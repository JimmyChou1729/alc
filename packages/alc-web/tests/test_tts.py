"""Offline HTTP contract tests; no model or installer is invoked."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from alc_web.tts import register_tts_routes


class FakeManager:
    def __init__(self):
        self.calls = []
        self.error = None
        self.configuration = {"enabled": False, "voice_zh": "zf_xiaobei", "voice_en": "af_heart"}

    def status(self):
        return {**self.configuration, "installed": False, "install": {"state": "idle", "message": ""}}

    def configure(self, **kwargs):
        self.calls.append(("configure", kwargs))
        self.configuration.update(kwargs)

    def install(self, **kwargs):
        self.calls.append(("install", kwargs))
        return self.status()

    def models(self):
        return [{"id": "test", "installed": False}]

    def preview(self, model_id=None, cancel_event=None, **kwargs):
        return self.synthesize(**kwargs)

    def synthesize(self, **kwargs):
        if self.error:
            raise self.error
        self.calls.append(("synthesize", kwargs))
        return b"RIFF-test-WAVE"


@pytest.fixture
def tts():
    manager = FakeManager()
    app = FastAPI()
    register_tts_routes(app, manager)
    with TestClient(app) as client:
        yield client, manager


@pytest.mark.parametrize("payload", [{}, {"confirmed": False}, {"confirmed": "true"}, {"confirmed": 1}])
def test_install_requires_explicit_boolean_confirmation(tts, payload):
    client, manager = tts
    assert client.post("/api/tts/install", json=payload).status_code in {400, 422}
    assert not manager.calls


def test_confirmed_install_and_configuration(tts):
    client, manager = tts
    assert client.get("/api/tts").json()["enabled"] is False
    assert client.post("/api/tts/install", json={"confirmed": True}).status_code == 202
    payload = {"enabled": True, "voice_zh": "zf_xiaobei", "voice_en": "af_heart"}
    assert client.patch("/api/tts", json=payload).json()["enabled"] is True
    assert manager.calls == [("install", {}), ("configure", payload)]


@pytest.mark.parametrize("payload", [
    {"text": ""}, {"text": "   "}, {"text": "x" * 2001},
    {"text": "hello", "language": "fr"}, {"text": "hello", "rate": 0},
    {"text": "hello", "rate": 3}, {"text": "hello", "url": "https://example.com"},
])
def test_preview_rejects_invalid_input_without_synthesis(tts, payload):
    client, manager = tts
    assert client.post("/api/tts/preview", json=payload).status_code in {400, 422}
    assert not manager.calls


def test_preview_returns_wav_and_preserves_selected_voice(tts):
    client, manager = tts
    payload = {"text": "Hello", "language": "en-US", "voice": "af_heart", "rate": 1.2}
    response = client.post("/api/tts/preview", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["cache-control"] == "no-store"
    assert response.content == b"RIFF-test-WAVE"
    assert manager.calls == [("synthesize", payload)]


def test_preview_reports_failure_without_fallback(tts):
    client, manager = tts
    manager.error = RuntimeError("本地模型未安装，请先安装。")
    response = client.post("/api/tts/preview", json={"text": "你好"})
    assert response.status_code == 503
    assert "请先安装" in response.json()["detail"]
    assert not manager.calls


def test_tts_routes_retain_application_authentication(tmp_path, monkeypatch):
    import alc_render.tts_engine
    from alc_web.app import create_app
    manager = FakeManager()
    manager.close = lambda: None
    monkeypatch.setattr(alc_render.tts_engine, "TTSManager", lambda: manager)
    origin = "http://127.0.0.1:8765"
    app = create_app(tmp_path, token="test-token", origin=origin, run_scheduler=False, discovered=[])
    with TestClient(app, base_url=origin) as client:
        assert client.get("/api/tts").status_code == 401
        assert client.post("/api/tts/install", json={"confirmed": True}).status_code == 401
        client.headers.update({"Authorization": "Bearer test-token", "Origin": "http://evil.test"})
        assert client.post("/api/tts/install", json={"confirmed": True}).status_code == 403
        client.headers["Origin"] = origin
        assert client.get("/api/tts").status_code == 200
        assert client.post("/api/tts/install", json={"confirmed": True}).status_code == 202
        assert manager.calls == [("install", {})]


def test_preview_does_not_require_or_change_enabled_state(tts):
    client, manager = tts
    response = client.post("/api/tts/preview", json={"text": "Hello", "language": "en-US"})
    assert response.status_code == 200
    assert float(response.headers["X-TTS-Synthesis-Ms"]) >= 0
    assert manager.configuration["enabled"] is False
    assert client.get("/api/tts/models").json()["models"][0]["id"] == "test"
    assert client.post("/api/tts/install", json={"confirmed": True, "model_id": "test"}).status_code == 202
    assert manager.calls[-1] == ("install", {"model_id": "test"})


def test_preview_passes_named_voice_and_model_without_configuration(tts):
    client, manager = tts
    requests = []
    manager.preview = lambda cancel_event=None, **kwargs: requests.append(kwargs) or b'RIFF-test-WAVE'
    payload = {'text': 'Hello from Kitten.', 'language': 'en-US',
               'model_id': 'kitten-tts-micro-0.8', 'voice': 'Jasper', 'rate': 1.0}
    response = client.post('/api/tts/preview', json=payload)
    assert response.status_code == 200
    assert requests == [payload]
    assert manager.configuration['enabled'] is False
    assert not manager.calls


def test_patch_accepts_only_independent_selections(tts):
    client, manager = tts
    selections = {"zh": None, "en": {"model_id": "kitten-tts-micro-0.8", "voice": "Jasper"}}
    response = client.patch("/api/tts", json={"selections": selections})
    assert response.status_code == 200
    assert manager.calls == [("configure", {"selections": selections})]


@pytest.mark.parametrize("payload", [{}, {"selections": None}, {"selections": {"zh": None}},
    {"selections": {"zh": None, "en": None, "extra": None}},
    {"selections": {"zh": None, "en": {"model_id": "kitten", "voice": 3}}},
    {"selections": {"zh": None, "en": {"model_id": "kitten", "voice": "Jasper", "url": "bad"}}},
])
def test_patch_rejects_incomplete_or_malformed_selections(tts, payload):
    client, manager = tts
    assert client.patch("/api/tts", json=payload).status_code == 422
    assert not manager.calls


def test_patch_real_manager_rejects_uninstalled_selection(tmp_path):
    from alc_render.tts_engine import TTSManager
    manager = TTSManager(tmp_path)
    app = FastAPI()
    register_tts_routes(app, manager)
    with TestClient(app) as client:
        response = client.patch("/api/tts", json={"selections": {"zh": None, "en": {"model_id": "kitten-tts-micro-0.8", "voice": "Jasper"}}})
    assert response.status_code == 400
    assert not (tmp_path / "settings.json").exists()


@pytest.mark.parametrize("payload", [{"enabled": True}, {"voice_en": "1"}, {"voice_zh": "3", "voice_en": "0"}])
def test_legacy_patch_requires_complete_configuration(tts, payload):
    client, manager = tts
    assert client.patch("/api/tts", json=payload).status_code == 422
    assert not manager.calls


def test_preview_asgi_disconnect_cancels_only_that_request():
    import asyncio
    import json
    import threading

    class Manager(FakeManager):
        started = threading.Event()
        cancelled = threading.Event()
        closed = False
        def preview(self, cancel_event=None, **kwargs):
            if kwargs["text"] == "disconnect this preview":
                self.started.set()
                assert cancel_event.wait(2)
                self.cancelled.set()
                raise RuntimeError("Cancelled")
            assert not cancel_event.is_set()
            return b"RIFF-test-WAVE"
        def close(self):
            self.closed = True

    manager = Manager()
    app = FastAPI()
    register_tts_routes(app, manager)

    async def run():
        incoming = asyncio.Queue()
        body = json.dumps({"text": "disconnect this preview"}).encode()
        await incoming.put({"type": "http.request", "body": body, "more_body": False})
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                 "method": "POST", "scheme": "http", "path": "/api/tts/preview",
                 "raw_path": b"/api/tts/preview", "query_string": b"",
                 "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
                 "server": ("testserver", 80), "client": ("127.0.0.1", 1)}
        sent = []
        async def send(message):
            sent.append(message)
        task = asyncio.create_task(app(scope, incoming.get, send))
        for _ in range(200):
            if manager.started.is_set():
                break
            await asyncio.sleep(0.005)
        assert manager.started.is_set()
        await incoming.put({"type": "http.disconnect"})
        await asyncio.wait_for(task, 3)
        assert manager.cancelled.is_set()
        assert not manager.closed
    asyncio.run(run())
    with TestClient(app) as client:
        assert client.post("/api/tts/preview", json={"text": "another reader"}).status_code == 200
    assert not manager.closed
