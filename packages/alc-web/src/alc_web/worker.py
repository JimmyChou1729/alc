"""One process per job; package CLIs own semantic execution and recovery."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import io
import json
import os
import shutil
import threading
import time
import tempfile
from pathlib import Path

from ac_jobs import FileLease, StoppedError
from ac_jobs.storage import atomic_write_json
from ac_llm import (
    HostAuthority,
    LLMExecutionOptions,
    LLMExecutionProfile,
)

from .acquisition import NeedsSourceInput, PDFTextConfirmation, acquire
from .store import Store


class PackagePaused(RuntimeError):
    def __init__(self, result: dict):
        self.result = result
        super().__init__("The workflow needs attention before it can continue.")


class DeliveryFailed(RuntimeError):
    pass


def call_cli(name: str, args: list[str], *, sink=None, options=None) -> dict:
    module = importlib.import_module(name.replace("-", "_") + ".cli")
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        if name in {"alc-companion", "alc-translate"}:
            code = module.main(args, event_sink=sink, llm_options=options)
        else:
            code = module.main(args)
    try:
        result = json.loads(stream.getvalue())
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} did not return its documented result.") from exc
    status = (result.get("data", {}).get("run") or {}).get("status")
    if (
        status in {"paused", "failed"}
        or result.get("status") in {"paused", "failed"}
        or code
    ):
        raise PackagePaused(result)
    return result


class Worker:
    def __init__(self, store: Store, job_id: str):
        self.store, self.job_id = store, job_id
        self.job = store.get(job_id)
        self.root = store.job_directory(job_id)
        self.project = self.root / "project"
        self.publication = self.project / "publication"
        self.cache = store.project / ".ac" / "cache" / "ac-document"
        self.active_owner: str | None = None
        self.last_progress = 0.0
        self.done = threading.Event()
        self.detail = self.job["detail"] or {}
        limits = store.setting("resources", {"api_slots": 8, "cli_slots": 8})
        self.window_workers = limits.get("translation_window_workers", 1)
        self.companion_workers = limits.get("companion_workers", 2)
        speed = self.job["spec"].get("speed")
        if speed is not None:
            self.window_workers = self.companion_workers = {"economy": 1, "standard": 2, "fast": 4}[speed]
        if self.job["spec"].get("processing_workers") is not None:
            self.window_workers = self.companion_workers = self.job["spec"]["processing_workers"]
        self.window_workers = min(self.window_workers, 8)
        self.companion_workers = min(self.companion_workers, 8)
        self.options = LLMExecutionOptions(
            host_authority=HostAuthority.UNKNOWN,
            profile=LLMExecutionProfile.LOCAL_APP,
            internet=False,
        )

    def capture_partial(self, result):
        progress = result.get("data", {}).get("progress", {})
        candidate = progress.get("partial_reader_path")
        if not candidate:
            return
        path = Path(candidate).resolve()
        if (not path.is_relative_to(self.root.resolve())
            or path.parent.name != "partial-reader" or path.name != "companion.html"):
            raise ValueError("Partial Reader path is outside the job")
        state_path = (path.parent / "state.json").resolve()
        if not state_path.is_relative_to(self.root.resolve()):
            raise ValueError("Partial Reader state is outside the job")
        if not state_path.is_file():
            return
        state = json.loads(state_path.read_text())
        payload = path.read_bytes()
        if (state.get("schema_version") != "alc.companion.partial_reader.v1"
            or state.get("sha256") != hashlib.sha256(payload).hexdigest()):
            raise ValueError("Partial Reader integrity check failed")
        from ac_jobs import atomic_write_bytes
        destination = self.store.project / "deliveries" / self.job_id / "partial-reader.html"
        destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(destination, payload)
        self.store.update(self.job_id, result={
            "reader": destination.relative_to(self.store.project).as_posix(),
            "sha256": state["sha256"], "size": len(payload), "partial": True,
            "unit_label": state.get("unit_label", "章节"),
            "completed_chapters": state["completed_chapters"],
            "total_chapters": state["total_chapters"],
            "incomplete_chapters": state["incomplete_chapters"],
        })


    def checkpoint(self):
        current = self.store.get(self.job_id)
        if current["control"] in {"pause", "cancel"}:
            raise StoppedError("User requested " + current["control"])

    def phase(self, phase: str):
        self.checkpoint()
        self.store.update(self.job_id, phase=phase)

    def sink(self, event: dict):
        self.store.event(
            self.job_id,
            "package.event",
            event,
            source_key=f"{self.job_id}:{self.active_owner}:{event['run_id']}:{event['event_id']}",
        )
        if self.active_owner == "translate" and event["event"] in {
            "glossary_progress",
            "translation_progress",
        }:
            self.detail["progress"] = event["data"]
            self.store.update(self.job_id, detail=self.detail)
        if time.monotonic() - self.last_progress > 1:
            self.last_progress = time.monotonic()
            if self.active_owner == "companion":
                from alc_companion import CompanionProjectPaths, CompanionService

                paths = CompanionProjectPaths.load(self.project)
                self.detail["progress"] = CompanionService(paths.jobs_root).progress(
                    event["run_id"]
                )
                self.store.update(self.job_id, detail=self.detail)

    def monitor(self):
        while not self.done.wait(0.5):
            try:
                current = self.store.get(self.job_id)
                if current["control"] in {"pause", "cancel"}:
                    self.stop_package()
            except (OSError, ValueError, KeyError):
                continue

    def stop_package(self):
        if self.active_owner == "companion":
            from alc_companion import CompanionProjectPaths, CompanionService

            paths = CompanionProjectPaths.load(self.project)
            if paths.current_run_id:
                CompanionService(paths.jobs_root).stop(
                    paths.current_run_id, reason="ALC Web requested stop"
                )
        elif self.active_owner == "translate":
            from alc_translate.project import TranslationProject
            from alc_translate.service import TranslationService

            paths = TranslationProject.load(self.publication)
            if paths.current_run_id:
                TranslationService(paths.jobs_root).stop(
                    paths.current_run_id, reason="ALC Web requested stop"
                )

    def model_args(self):
        spec = self.job["spec"]
        args = [
            "--provider",
            spec["provider_id"],
            "--model",
            spec["model"],
            "--processing-mode",
            spec["mode"],
            "--user-intent",
            spec["user_intent"],
        ]
        if spec.get("review_rounds") is not None:
            args += ["--review-rounds", str(spec["review_rounds"])]
        if spec.get("reasoning_effort"):
            args += ["--reasoning-effort", spec["reasoning_effort"]]
        return args

    def stage(self, name: str, command: list[str], *, step: str | None = None):
        self.checkpoint()
        receipt = self.root / "stages" / f"{name}.json"
        if receipt.exists():
            # get-result verifies the selected immutable artifact before replay.
            if step:
                call_cli(
                    "alc-translate",
                    [
                        "get-result",
                        "--project-dir",
                        str(self.publication),
                        "--step",
                        step,
                    ],
                )
            return json.loads(receipt.read_text())
        owner = "alc-companion" if self.active_owner == "companion" else "alc-translate"
        project = self.project if self.active_owner == "companion" else self.publication
        if self.job["generation"] > 1:
            try:
                status = call_cli(owner, ["status", "--project-dir", str(project)])
            except PackagePaused as exc:
                status = exc.result
            data = status.get("data", {})
            current = data.get("selected_run") or data.get("run") or {}
            if current.get("status") in {"paused", "failed"} and (
                step is None or data.get("current_step") == step
            ):
                command = [
                    "resume",
                    "--project-dir",
                    str(project),
                    "--document-cache-root",
                    str(self.cache),
                    "--host-authority",
                    "unknown",
                ]
                if owner == "alc-companion":
                    command += ["--workers", str(self.companion_workers)]
                if self.job.get("resume_input") is not None:
                    command += ["--input", json.dumps(self.job["resume_input"])]
        if owner == "alc-companion" and self.job["spec"].get("preload_chapter_evidence"):
            command = [*command, "--preload-chapter-evidence"]
        if owner == "alc-translate":
            command = [*command, "--window-workers", str(self.window_workers)]
        result = call_cli(owner, command, sink=self.sink, options=self.options)
        atomic_write_json(receipt, result)
        return result

    def run(self):
        self.phase("acquisition")
        source, manifest, warnings = acquire(self.store, self.job, self.checkpoint)
        self.detail["source_warnings"] = warnings
        self.detail["source_preview"] = source.read_text(encoding="utf-8")[:3000]
        self.detail["source_bytes"] = source.stat().st_size
        self.store.update(self.job_id, detail=self.detail)
        spec = self.job["spec"]
        self.phase("parse")
        from ac_document import AcDocumentService
        from .estimates import estimate_document

        parsed = AcDocumentService(cache_root=self.cache).parse_local(source).document
        self.detail["source_preview"] = "\n\n".join(section.text for section in parsed.sections)[:3000]
        from .presentation import source_title
        title = source_title(source) or next((section.title for section in parsed.sections if section.level == 1 and section.title.strip()), "")
        if title:
            self.detail["document_title"] = title[:500]
        self.detail["document_bytes"] = len("\n".join(section.text for section in parsed.sections).encode("utf-8"))
        self.detail["estimate"] = estimate_document(
            "\n".join(section.text for section in parsed.sections), spec
        )
        self.store.update(self.job_id, detail=self.detail)
        if spec["output"] == "companion":
            self.active_owner = "companion"
            self.phase("companion")
            args = [
                "build",
                str(source),
                "--project-dir",
                str(self.project),
                "--target-language",
                spec["target_language"],
                "--user-intent",
                spec["user_intent"],
                "--document-cache-root",
                str(self.cache),
                "--host-authority",
                "unknown",
                "--workers",
                str(self.companion_workers),
                *self.model_args(),
            ]
            if manifest:
                args += ["--html-source-manifest", str(manifest)]
            result = self.stage("companion", args)
            self.phase("render")
            result = call_cli(
                "alc-companion", ["render", "--project-dir", str(self.project)]
            )
            html = result.get("data", {}).get("delivery", {}).get("html")
            if not html:
                raise DeliveryFailed(
                    "Generation is saved, but Reader rendering or promotion failed."
                )
            reader = Path(html)
            publications = [
                Path(item["path"])
                for item in result.get("artifacts", [])
                if item.get("role") == "publication"
            ]
            if len(publications) != 1:
                raise DeliveryFailed("Rendered publication identity is unavailable.")
            composed = publications[0]
        else:
            from ac_document import AcDocumentService

            if not (self.publication / "rich-source.json").exists():
                exported = self.root / "source-export"
                if not (exported / "rich-source.json").exists():
                    export_result = AcDocumentService(
                        cache_root=self.cache
                    ).export_rich_document(source, output_dir=exported)
                    self.detail["parse_warnings"] = export_result.get("warnings", [])
                    self.store.update(self.job_id, detail=self.detail)
                if spec["output"] == "reader":
                    from alc_translate.project import TranslationProject

                    TranslationProject.open(self.publication)
                self.publication.mkdir(parents=True, exist_ok=True)
                for item in exported.iterdir():
                    if item.is_dir():
                        shutil.copytree(item, self.publication / item.name)
                    else:
                        shutil.copy2(item, self.publication / item.name)
            if spec["output"] == "reader":
                self.active_owner = "translate"
                common = [
                    str(source),
                    "--project-dir",
                    str(self.publication),
                    "--document-cache-root",
                    str(self.cache),
                    "--host-authority",
                    "unknown",
                    *self.model_args(),
                ]
                for phase, command, step in (
                    ("language", "detect-language", "language"),
                    ("glossary", "build-glossary", "glossary"),
                    ("translation", "translate-blocks", "blocks"),
                ):
                    self.phase(phase)
                    args = [command, *common]
                    if phase == "language":
                        args += ["--target-language", spec["target_language"]]
                    self.stage(phase, args, step=step)
                    if phase == "language":
                        language = call_cli(
                            "alc-translate",
                            [
                                "get-result",
                                "--project-dir",
                                str(self.publication),
                                "--step",
                                "language",
                            ],
                        )
                        if language["data"]["result"]["mode"] == "skipped":
                            break
            self.phase("render")
            composed = self.publication / "publication.json"
            compose = [
                "compose",
                "--source",
                str(self.publication / "rich-source.json"),
                "--metadata",
                str(self.publication / "metadata.json"),
                "--output",
                str(composed),
            ]
            layer, glossary = (
                self.publication / "translation.layer.json",
                self.publication / "translation.glossary.json",
            )
            if layer.exists():
                compose += ["--layer", str(layer)]
            if glossary.exists():
                compose += ["--glossary", str(glossary)]
            call_cli("alc-render", compose)
            reader = self.project / "reader.html"
            call_cli(
                "alc-render",
                ["render", "--publication", str(composed), "--html", str(reader)],
            )
            self.phase("validate")
            call_cli(
                "alc-render",
                ["validate", "--publication", str(composed), "--html", str(reader)],
            )
        self.checkpoint()
        if (
            not reader.resolve().is_relative_to(self.root.resolve())
            or not reader.is_file()
        ):
            raise DeliveryFailed("Reader path is outside this job.")
        from alc_render import publication_translation_quality

        if not composed.resolve().is_relative_to(self.root.resolve()):
            raise DeliveryFailed("Publication path is outside this job.")
        quality = publication_translation_quality(composed)
        warnings = list(
            dict.fromkeys([*warnings, *self.detail.get("parse_warnings", [])])
        )
        destination = self.store.project / "deliveries" / self.job_id / "reader.html"
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = reader.read_bytes()
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=".reader-", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(destination)
        self.store.finish(
            self.job_id,
            {
                "reader": destination.relative_to(self.store.project).as_posix(),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size": len(payload),
                "quality": quality,
                "publication": composed.relative_to(self.store.project).as_posix(),
                "warnings": warnings,
            },
        )


def execute(project: str, job_id: str, generation: int | None = None):
    store = Store(project)
    root = store.job_directory(job_id)
    root.mkdir(parents=True, exist_ok=True)
    lease = FileLease(root / "worker.lock").acquire(blocking=True)
    current = store.get(job_id)
    if current["state"] != "running" or (
        generation is not None and current["generation"] != generation
    ):
        lease.release()
        return
    from .runtime import runtime_identity

    current_runtime = runtime_identity()
    if (current["spec"].get("runtime") != current_runtime
        and not store.bind_unstarted_runtime(job_id, current_runtime)):
        store.update(
            job_id,
            state="needs_input",
            error={
                "code": "runtime_changed",
                "message": "The task runtime has changed or was not recorded. Restore the original environment to resume, or create a new task with the current runtime.",
            },
        )
        lease.release()
        return
    worker = Worker(store, job_id)
    monitor = threading.Thread(target=worker.monitor, daemon=True)
    monitor.start()
    try:
        worker.run()
    except StoppedError:
        state = "cancelled" if store.get(job_id)["control"] == "cancel" else "paused"
        store.update(job_id, state=state)
    except PackagePaused as exc:
        try:
            worker.capture_partial(exc.result)
        except (OSError, ValueError, KeyError, TypeError) as partial_error:
            store.event(job_id, "partial_reader_unavailable", {"type": type(partial_error).__name__})
        current = store.get(job_id)
        state = (
            "cancelled"
            if current["control"] == "cancel"
            else "paused" if current["control"] == "pause" else "needs_input"
        )
        result = exc.result
        store.update(
            job_id,
            state=state,
            error={
                "code": "workflow_attention",
                "message": str(exc),
                "workflow_error": result.get("error"),
                "resume": result.get("resume"),
                "data": result.get("data"),
            },
        )
    except PDFTextConfirmation as exc:
        store.update(
            job_id,
            state="needs_input",
            error={"code": "pdf_text_confirmation", "message": str(exc)},
        )
    except NeedsSourceInput as exc:
        store.update(
            job_id,
            state="needs_input",
            error={"code": "source_attention", "message": str(exc)},
        )
    except DeliveryFailed as exc:
        store.update(
            job_id,
            state="delivery_failed",
            error={"code": "delivery_failed", "message": str(exc)},
        )
    except Exception as exc:
        from ac_llm.diagnostics import redact_text

        state = (
            "delivery_failed"
            if store.get(job_id)["phase"] in {"render", "validate"}
            else "failed"
        )
        store.update(
            job_id,
            state=state,
            error={
                "code": "local_error",
                "message": redact_text(str(exc))[:1500],
                "type": type(exc).__name__,
            },
        )
    finally:
        try:
            store.schedule_recovery(job_id)
        finally:
            worker.done.set()
            monitor.join(timeout=2)
            lease.release()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--generation", required=True, type=int)
    args = parser.parse_args()
    execute(args.project_dir, args.job_id, args.generation)
