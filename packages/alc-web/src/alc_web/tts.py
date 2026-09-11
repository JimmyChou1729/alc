"""TTS management routes protected by the application's HTTP boundary."""

from typing import Literal
import asyncio
from contextlib import suppress
import threading
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator


class TTSVoiceSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(min_length=1, max_length=100)
    voice: str = Field(min_length=1, max_length=100)


class TTSSelections(BaseModel):
    model_config = ConfigDict(extra="forbid")
    zh: TTSVoiceSelection | None
    en: TTSVoiceSelection | None


class TTSConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool = False
    voice_zh: str = Field(default="3", min_length=1, max_length=100)
    voice_en: str = Field(default="0", min_length=1, max_length=100)
    selections: TTSSelections | None = None

    @field_validator("selections")
    @classmethod
    def selections_not_null(cls, value):
        if value is None:
            raise ValueError("Selections must include zh and en")
        return value

    @model_validator(mode="after")
    def configuration_not_empty(self):
        if "selections" not in self.model_fields_set and not {"enabled", "voice_zh", "voice_en"}.issubset(self.model_fields_set):
            raise ValueError("Provide selections or complete legacy enabled/voice_zh/voice_en configuration")
        return self


class TTSInstall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: StrictBool = False
    model_id: str | None = Field(default=None, min_length=1, max_length=100)


class TTSPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)
    language: Literal["zh-CN", "en-US"] = "zh-CN"
    voice: str | None = Field(default=None, min_length=1, max_length=100)
    rate: float = Field(default=1.0, ge=0.5, le=2.0)
    model_id: str | None = Field(default=None, min_length=1, max_length=100)


def register_tts_routes(app: FastAPI, manager) -> None:
    def invoke(action, **kwargs):
        try:
            return action(**kwargs)
        except ValueError as exc:
            raise HTTPException(400, str(exc)[:1000]) from None
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)[:1000]) from None

    @app.get("/api/tts")
    def status():
        return invoke(manager.status)

    @app.get("/api/tts/models")
    def models():
        return {"models": invoke(manager.models)}

    @app.patch("/api/tts")
    def configure(value: TTSConfiguration):
        invoke(manager.configure, **value.model_dump(exclude_unset=True))
        return invoke(manager.status)

    @app.post("/api/tts/install", status_code=202)
    def install(value: TTSInstall):
        if not value.confirmed:
            raise HTTPException(400, "请先确认下载并安装本地朗读模型。")
        kwargs = {"model_id": value.model_id} if value.model_id else {}
        return invoke(manager.install, **kwargs)

    @app.post("/api/tts/preview")
    async def preview(value: TTSPreview, request: Request):
        if not value.text.strip():
            raise HTTPException(400, "请输入试听文字。")
        start = time.perf_counter()
        cancelled = threading.Event()

        async def watch_disconnect():
            while not cancelled.is_set():
                if await request.is_disconnected():
                    cancelled.set()
                    return
                await asyncio.sleep(0.1)

        watcher = asyncio.create_task(watch_disconnect())
        try:
            audio = await run_in_threadpool(invoke, manager.preview, **value.model_dump(), cancel_event=cancelled)
        finally:
            # Also cancel inference if the ASGI task is cancelled during server shutdown.
            cancelled.set()
            watcher.cancel()
            with suppress(asyncio.CancelledError):
                await watcher
        elapsed_ms = (time.perf_counter() - start) * 1000
        return Response(
            audio, media_type="audio/wav",
            headers={"Cache-Control": "no-store", "X-TTS-Synthesis-Ms": f"{elapsed_ms:.1f}"},
        )
