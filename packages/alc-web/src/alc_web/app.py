"""Loopback-only HTTP interface and authenticated event stream."""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from ac_document import load_mineru_config
from alc_catalog.mineru import effective_config_path, remember_local_config

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .acquisition import normalize_source_url
from .metrics import summarize
from .models import ControlInput, JobInput, ProviderInput, ResourceInput, OCRInput
from .providers import (
    SecretVault,
    cli_profiles,
    present_profile,
    resolve_profile,
    runtime_profile,
    save_provider,
    validate_model_effort,
)
from .scheduler import Scheduler
from .store import Store
from .runtime import runtime_identity
from .reader_host import ReaderHosts

class HistoryProjectInput(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


class RenameInput(BaseModel):
    title: str = Field(min_length=1, max_length=500)


EXTENSIONS = {".md", ".markdown", ".html", ".htm", ".pdf", ".tex"}


def create_app(
    project: str | Path,
    *,
    token: str,
    origin: str,
    run_scheduler: bool = True,
    discovered: list[dict] | None = None,
) -> FastAPI:
    from ac_llm import LLMExecutionProfile

    if not hasattr(LLMExecutionProfile, "LOCAL_APP"):
        raise RuntimeError(
            "ALC Web requires the matching AC Foundation application runtime; see packages/alc-web/README.md."
        )
    store = Store(project)
    vault = SecretVault(store.project)
    cookie_name = "alc_session_" + hashlib.sha256(origin.encode()).hexdigest()[:12]
    profiles = cli_profiles() if discovered is None else discovered
    scheduler = Scheduler(store, vault)
    reader_hosts = ReaderHosts(store.root / "reader-ports.json")

    @asynccontextmanager
    async def lifespan(app):
        if run_scheduler:
            scheduler.start()
        try:
            yield
        finally:
            reader_hosts.close()
            if run_scheduler:
                scheduler.close()

    app = FastAPI(
        title="ALC Local Web",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.store, app.state.vault = store, vault

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        if request.headers.get("host") != origin.removeprefix("http://"):
            return JSONResponse({"error": "Invalid Host."}, status_code=403)
        path = request.url.path
        if path.startswith("/api/"):
            supplied = request.headers.get("authorization", "").removeprefix(
                "Bearer "
            ) or request.cookies.get(cookie_name, "")
            if not supplied or not secrets.compare_digest(supplied, token):
                return JSONResponse(
                    {"error": "Open ALC using the local launch command."},
                    status_code=401,
                )
            if request.headers.get("origin") not in {None, origin} or (
                request.method not in {"GET", "HEAD", "OPTIONS"}
                and request.headers.get("origin") != origin
            ):
                return JSONResponse({"error": "Invalid Origin."}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse(
                {"error": "Cross-site access refused."}, status_code=403
            )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = (
            "no-store" if path.startswith("/api/") else "no-cache"
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def input_error(request, exc):
        # Pydantic errors can contain submitted secrets in their input field.
        return JSONResponse(
            {
                "error": ("Base URL 应填写服务根地址（例如 https://api.example.com/v1），不要包含完整接口路径；请同时核对协议类型。" if any("base_url" in e["loc"] or "Base URL 应填写" in e.get("msg", "") for e in exc.errors()) else "输入不符合要求，请检查标记的字段。"),
                "fields": [list(e["loc"]) for e in exc.errors()],
            },
            status_code=422,
        )

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse({"error": str(exc)[:1000]}, status_code=400)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"error": "Requested item was not found."}, status_code=404)

    @app.get("/health")
    def health():
        return {
            "application": "alc-web",
            "ready": True,
            "instance": hashlib.sha256(token.encode()).hexdigest(),
        }

    @app.post("/api/session")
    def session():
        response = JSONResponse({"ready": True})
        response.set_cookie(
            cookie_name, token, httponly=True, samesite="strict", path="/api/"
        )
        return response

    @app.get("/api/settings")
    def settings():
        custom = [
            {
                **present_profile(p),
                "key_available": vault.availability(
                    p.get("secret_ref", p["id"]),
                    remember=p.get("remember_key", False),
                ),
                "authentication": "not_verified",
            }
            for p in store.setting("providers", {}).values()
        ]
        return {
            "providers": profiles + custom,
            "resources": {
                **ResourceInput().model_dump(),
                **store.setting("resources", {}),
            },
            "project": str(store.project),
            "ocr": load_mineru_config(effective_config_path(store.project)),
        }

    @app.post("/api/ocr")
    def ocr_settings(value: OCRInput):
        from ac_document import configure_mineru
        try:
            result = configure_mineru(config_path=store.project / ".ac" / "mineru.json", **value.model_dump())
            remember_local_config(value.model_dump())
            return result
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.post("/api/ocr/doctor")
    def ocr_doctor():
        from ac_document import doctor_configured_mineru
        try:
            return doctor_configured_mineru(config_path=effective_config_path(store.project))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.post("/api/providers")
    def provider(value: ProviderInput):
        return save_provider(store, vault, value)

    @app.post("/api/resources")
    def resources(value: ResourceInput):
        old = {**ResourceInput().model_dump(), **store.setting("resources", {})}
        if (
            any(old[k] != getattr(value, k) for k in (
                "api_slots", "cli_slots", "translation_window_workers", "companion_workers"
            ))
            and store.active_ids()
        ):
            raise ValueError(
                "Pause running tasks before changing provider slot or translation window limits. All active workers must share one admission policy."
            )
        store.save_setting("resources", value.model_dump())
        return value.model_dump()

    @app.post("/api/sources")
    async def upload(file: UploadFile = File(...)):
        name = Path(file.filename or "").name
        if (
            not name
            or name != file.filename
            or Path(name).suffix.lower() not in EXTENSIONS
        ):
            raise ValueError(
                "Upload a PDF, HTML, Markdown or single-file TeX document."
            )
        source_id = uuid.uuid4().hex
        directory = store.root / "uploads" / source_id
        directory.mkdir(parents=True, mode=0o700)
        path, count, digest = directory / name, 0, hashlib.sha256()
        try:
            with path.open("xb") as handle:
                while chunk := await file.read(1024 * 1024):
                    count += len(chunk)
                    digest.update(chunk)
                    handle.write(chunk)
            if not count:
                raise ValueError("The uploaded document is empty.")
            source = {
                "id": source_id,
                "name": name,
                "path": path.relative_to(store.root).as_posix(),
                "bytes": count,
                "sha256": digest.hexdigest(),
            }
            store.add_source(source_id, source)
        except BaseException:
            path.unlink(missing_ok=True)
            directory.rmdir()
            raise
        finally:
            await file.close()
        return {k: v for k, v in source.items() if k != "path"}

    from .history import history_jobs, history_job, import_project

    @app.post("/api/history/projects")
    def add_history_project(value: HistoryProjectInput):
        return import_project(value.path)

    @app.get("/api/jobs")
    def jobs():
        combined = store.summaries() + history_jobs(store)
        return sorted(combined, key=lambda j: j["created"], reverse=True)

    @app.post("/api/jobs", status_code=201)
    def new_job(value: JobInput):
        spec = value.model_dump()
        uploaded = store.source(value.source_id) if value.source_id else None
        may_be_pdf = uploaded is None or Path(uploaded["name"]).suffix.lower() == ".pdf"
        spec["ocr"] = load_mineru_config(effective_config_path(store.project)) if value.pdf_mode == "mineru" and may_be_pdf else None
        if spec["ocr"] and spec["ocr"]["api_url"] and (not value.ocr_remote_consent or value.ocr_service_url != spec["ocr"]["api_url"]):
            raise HTTPException(400, "Refresh settings and confirm uploading PDF files to the selected MinerU service.")
        spec["runtime"] = runtime_identity()
        spec["automatic_recovery"] = True
        if value.output == "companion":
            spec["preload_chapter_evidence"] = True
        if value.source_id:
            source = store.source(value.source_id)
            spec["title"] = source["name"]
        else:
            spec["source_url"] = normalize_source_url(value.source_url)
            spec["title"] = spec["source_url"]
        if value.ocr_proofread and (value.pdf_mode != "mineru" or spec["ocr"] is None or not may_be_pdf):
            raise HTTPException(400, "OCR proofreading requires a PDF source and configured MinerU.")
        if value.output != "source" or value.ocr_proofread:
            profile = resolve_profile(store, value.provider_id, profiles)
            if profile["protocol"] == "cli":
                spec["model"] = (
                    value.model or profile.get("default_model") or profile["model"]
                )
            else:
                spec["model"] = value.model or profile["model"]
            validate_model_effort(profile, spec["model"], value.reasoning_effort)
            if not spec.get("reasoning_effort"):
                selected = next((m for m in profile.get("models", []) if m.get("id") == spec["model"]), {})
                default_effort = selected.get("default_reasoning_effort")
                if default_effort:
                    validate_model_effort(profile, spec["model"], default_effort)
                    spec["reasoning_effort"] = default_effort
            if value.ocr_proofread:
                if (not value.ocr_proofread_consent or value.ocr_proofread_provider_id != value.provider_id
                        or not value.ocr_proofread_model or value.ocr_proofread_model != spec["model"]):
                    raise HTTPException(400, "Confirm sending PDF page images to the selected proofreading model.")
                if profile["protocol"] != "cli" and not profile.get("vision"):
                    raise HTTPException(400, "The selected API provider must support image input for OCR proofreading.")
            spec["provider"] = runtime_profile(profile)
        else:
            spec["provider"] = {"protocol": "none"}
        return public_job(store.create(spec))

    def public_job(job):
        result = {k: v for k, v in job.items() if k != "resume_input"}
        result["metrics"] = summarize(store, job)
        from .presentation import source_warning_messages, translation_notice
        raw_warnings = (job.get("result") or {}).get("warnings") or (job.get("detail") or {}).get("source_warnings") or []
        result["source_messages"] = source_warning_messages(raw_warnings)
        result["translation_notice"] = translation_notice(store, job)
        from .event_labels import event_label
        result["recent_events"] = [dict(e, label=event_label(e)) for e in store.recent_events(job["id"])]
        return result

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        if job_id.startswith("agent-"):
            return history_job(store, job_id)
        return public_job(store.get(job_id))

    @app.get("/api/jobs/{job_id}/ocr-notices")
    def ocr_notices(job_id: str):
        from .ocr_review import _selection
        from .ocr_notices import summarize_notices
        service, run_id, _ = _selection(store, store.get(job_id))
        return summarize_notices(service.result(run_id))

    @app.patch("/api/jobs/{job_id}")
    def rename_job(job_id: str, value: RenameInput):
        if job_id.startswith("agent-"):
            raise HTTPException(409, "Agent history is read-only; use the original plugin to manage this task.")
        return public_job(store.rename(job_id, value.title))

    @app.delete("/api/jobs/{job_id}")
    def delete_job(job_id: str):
        if job_id.startswith("agent-"):
            raise HTTPException(409, "Agent history is read-only; use the original plugin to manage this task.")
        store.delete(job_id)
        return {"deleted": True}

    @app.post("/api/jobs/{job_id}/control")
    def control(job_id: str, value: ControlInput):
        if job_id.startswith("agent-"):
            raise HTTPException(409, "Agent history is read-only; use the original plugin to manage this task.")
        job = store.get(job_id)
        if value.action == "resume" and (job.get("error") or {}).get("code") == "ocr_review_required":
            from .ocr_review import resume_completed_ocr
            return public_job(resume_completed_ocr(store, job))
        return public_job(store.control(job_id, value.action, value.resume_input))

    @app.get("/api/jobs/{job_id}/events")
    async def events(job_id: str, request: Request):
        store.get(job_id)
        try:
            after = int(request.headers.get("last-event-id", "0"))
            if after < 0:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "Invalid event cursor.")

        async def stream():
            cursor, idle = after, 0
            while not await request.is_disconnected():
                rows = await asyncio.to_thread(store.events, job_id, cursor)
                for event in rows:
                    cursor = event["sequence"]
                    yield f"id: {cursor}\nevent: update\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                if not rows:
                    idle += 1
                    if idle % 20 == 0:
                        yield ": heartbeat\n\n"
                    await asyncio.sleep(0.5)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"},
        )

    @app.get("/api/jobs/{job_id}/artifact")
    def history_artifact(job_id: str):
        from .history import artifact_path
        path = artifact_path(store, job_id)
        return FileResponse(path, media_type="application/octet-stream", filename="task-result.json")

    @app.get("/api/jobs/{job_id}/reader")
    def reader(job_id: str, download: bool = False):
        if job_id.startswith("agent-"):
            from .history import reader_path
            path = reader_path(store, job_id)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if not download:
                return RedirectResponse(reader_hosts.open(path, digest), status_code=307)
            return FileResponse(path, media_type="text/html", filename="reader.html",
                headers={"Content-Security-Policy": "sandbox"})
        job = store.get(job_id)
        result = job.get("result")
        if not result:
            raise HTTPException(404, "A verified Reader is not available yet.")
        path = (store.project / result["reader"]).resolve()
        if (
            not path.is_relative_to((store.project / "deliveries" / job_id).resolve())
            or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != result["sha256"]
        ):
            raise HTTPException(
                409, "Reader bytes no longer match the verified delivery."
            )
        if not download:
            return RedirectResponse(reader_hosts.open(path, result["sha256"]), status_code=307)
        return FileResponse(
            path,
            media_type="text/html",
            filename="reader.html" if download else None,
            headers={
                "Content-Security-Policy": "sandbox allow-scripts allow-downloads allow-modals; default-src 'none'; script-src 'unsafe-inline' blob:; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'"
            },
        )

    static = Path(__file__).parent / "static"
    if static.is_dir():
        app.mount("/", StaticFiles(directory=static, html=True), name="web")
    else:

        @app.get("/")
        def missing_assets():
            return JSONResponse(
                {
                    "error": "Web assets are missing. Run the documented frontend build before starting the source checkout."
                },
                status_code=503,
            )

    return app
