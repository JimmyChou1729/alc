"""Single-instance supervisor with bounded, separately recoverable job processes."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

from ac_jobs.storage import atomic_write_json


class Scheduler:
    def __init__(self, store, vault):
        self.store, self.vault = store, vault
        self.processes: dict[str, tuple[subprocess.Popen, object]] = {}
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self.loop, daemon=True)

    def start(self):
        self.reconcile()
        self.thread.start()

    def reconcile(self):
        for job_id in self.store.active_ids():
            if job_id in self.processes:
                continue
            job = self.store.get(job_id)
            if job["state"] in {"running", "delivering", "pausing", "cancelling"}:
                # A worker lease survives the HTTP service. Never start a second writer.
                from ac_jobs import FileLease

                try:
                    lease = FileLease(
                        self.store.job_directory(job["id"]) / "worker.lock"
                    ).acquire(blocking=False)
                except Exception:
                    continue
                lease.release()
                state = "cancelled" if job["control"] == "cancel" else "paused"
                self.store.update(
                    job["id"],
                    state=state,
                    error={
                        "code": "interrupted",
                        "message": "Execution was interrupted. Resume verifies completed work before continuing.",
                    },
                )

    def loop(self):
        while not self.stopping.wait(0.3):
            try:
                for job_id, (process, output) in list(self.processes.items()):
                    if process.poll() is not None:
                        output.close()
                        del self.processes[job_id]
                        job = self.store.get(job_id)
                        if job["state"] in {
                            "running",
                            "pausing",
                            "cancelling",
                            "delivering",
                        }:
                            state = (
                                "cancelled"
                                if job["control"] == "cancel"
                                else "paused" if job["control"] == "pause" else "failed"
                            )
                            self.store.update(
                                job_id,
                                state=state,
                                error={
                                    "code": "worker_exited",
                                    "message": "The worker exited before completing delivery. Completed package work is retained.",
                                    "exit_code": process.returncode,
                                },
                            )
                self.store.resume_due_recoveries()
                maximum = self.store.setting("resources", {"max_jobs": 2})["max_jobs"]
                self.reconcile()
                active = len(self.store.active_ids())
                for job_id in self.store.pending_ids(maximum - active):
                    if job_id in self.processes:
                        continue
                    job = self.store.get(job_id)
                    if active >= maximum:
                        break
                    if job["state"] == "queued" and self.store.claim(job["id"]):
                        self.launch(self.store.get(job["id"]))
                        active += 1
            except Exception as exc:
                # Keep the supervisor alive; a later iteration can recover admission.
                self.store.save_setting(
                    "scheduler_error", {"type": type(exc).__name__, "at": time.time()}
                )

    def launch(self, job):
        profile = job["spec"].get("provider", {})
        env = dict(os.environ)
        env.pop("AC_LLM_PROVIDER_CONFIG", None)
        env.pop("AC_LLM_CALL_API_KEY", None)
        root = self.store.job_directory(job["id"])
        root.mkdir(parents=True, exist_ok=True)
        if profile.get("protocol") in {"responses", "chat-completions", "anthropic"}:
            key = self.vault.get(
                profile.get("secret_ref", profile["id"]),
                remember=profile.get("remember_key", False),
            )
            if not key:
                self.store.update(
                    job["id"],
                    state="needs_input",
                    error={
                        "code": "credential_required",
                        "message": "Configure or unlock the API credential, then resume.",
                    },
                )
                return
            config = {
                "name": profile["id"],
                "protocol": profile["protocol"],
                "base_url": profile["base_url"],
                "credential": {"kind": "environment", "name": "AC_LLM_CALL_API_KEY"},
                "max_output_tokens": profile["max_output_tokens"],
                "reasoning_efforts": profile["reasoning_efforts"],
                "vision": profile["vision"],
            }
            path = root / "provider.json"
            atomic_write_json(
                path, {"schema_version": "ac.llm.providers.v1", "providers": [config]}
            )
            env["AC_LLM_PROVIDER_CONFIG"] = str(path)
            env["AC_LLM_CALL_API_KEY"] = key
        output = (root / "worker.log").open("ab")
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "alc_web.worker",
                    "--project-dir",
                    str(self.store.project),
                    "--job-id",
                    job["id"],
                    "--generation",
                    str(job["generation"]),
                ],
                cwd=root,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except Exception:
            output.close()
            self.store.update(
                job["id"],
                state="failed",
                error={
                    "code": "worker_start_failed",
                    "message": "Could not start the job worker.",
                },
            )
            return
        self.processes[job["id"]] = (process, output)

    def close(self):
        self.stopping.set()
        self.thread.join(timeout=2)
        # Workers keep their leases and durable queue connection after a UI restart.
        for _, output in self.processes.values():
            output.close()
