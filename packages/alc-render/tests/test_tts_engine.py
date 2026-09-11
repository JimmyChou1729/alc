"""Offline tests: never install runtime packages or download the real model."""
import io
from pathlib import Path
import tarfile
import threading

import pytest

from alc_render import tts_engine as tts


def test_status_has_no_side_effects(tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "_download_model", lambda _: pytest.fail("network"))
    root = tmp_path / "absent"
    manager = tts.TTSManager(root)
    result = manager.status()
    assert result["enabled"] is False
    assert result["installed"] is False
    assert result["install"]["state"] == "idle"
    assert result["model"]["download_bytes"] == 147031220
    assert len(result["voices"]) == 103
    assert not root.exists()


def test_configuration_persists_and_environment_root(tmp_path, monkeypatch):
    monkeypatch.setenv("ALC_TTS_DIR", str(tmp_path))
    manager = tts.TTSManager()
    manager.configure(True, "3", "1")
    assert tts.TTSManager(tmp_path).status()["voice_en"] == "1"
    for args in [(1, "3", "0"), (True, "0", "1"), (True, "3", "../x")]:
        with pytest.raises(ValueError):
            manager.configure(*args)


def test_concurrent_install_and_retry(tmp_path, monkeypatch):
    manager = tts.TTSManager(tmp_path)
    other = tts.TTSManager(tmp_path)
    entered, finish = threading.Event(), threading.Event()
    calls = []

    def install(cancelled):
        calls.append(1)
        entered.set()
        assert finish.wait(5)
        raise RuntimeError("private credential must not escape")

    monkeypatch.setattr(manager._provider, "install", install)
    manager.install()
    assert entered.wait(5)
    assert other.install()["install"]["state"] == "running"
    assert len(calls) == 1
    finish.set()
    manager._install_thread.join(5)
    assert manager.status()["install"]["state"] == "failed"
    assert "credential" not in manager.status()["install"]["message"]
    monkeypatch.setattr(manager._provider, "install", lambda cancelled: None)
    manager.install()
    manager._install_thread.join(5)
    assert manager.status()["install"]["state"] == "completed"


@pytest.mark.parametrize("kind,name", [("file", "../escape"), ("file", "/escape"), ("symlink", "link"), ("hardlink", "link"), ("fifo", "pipe"), ("file", "C:/escape")])
def test_archive_rejects_unsafe_members(tmp_path, kind, name):
    archive = tmp_path / "bad.tar.bz2"
    member = tarfile.TarInfo(name)
    if kind == "symlink":
        member.type = tarfile.SYMTYPE
        member.linkname = "../escape"
    elif kind == "hardlink":
        member.type = tarfile.LNKTYPE
        member.linkname = "../escape"
    elif kind == "fifo":
        member.type = tarfile.FIFOTYPE
    with tarfile.open(archive, "w:bz2") as tar:
        tar.addfile(member, io.BytesIO())
    with pytest.raises(ValueError, match="Unsafe"):
        tts._safe_extract(archive, tmp_path / "out")
    assert not (tmp_path.parent / "escape").exists()


def test_completed_download_is_reused_and_checksum_enforced(tmp_path, monkeypatch):
    import hashlib
    path = tmp_path / "archive"
    path.write_bytes(b"verified")
    monkeypatch.setattr(tts, "MODEL_SHA256", hashlib.sha256(b"verified").hexdigest())
    monkeypatch.setattr(tts, "build_opener", lambda *_: pytest.fail("Should reuse download"))
    tts._download_model(path)


def test_synthesis_gates_and_cache_identity(tmp_path, monkeypatch):
    manager = tts.TTSManager(tmp_path)
    with pytest.raises(RuntimeError, match="disabled"):
        manager.synthesize("Hello")
    manager.configure(True, "3", "0")
    with pytest.raises(RuntimeError, match="Install"):
        manager.synthesize("Hello")
    monkeypatch.setattr(manager._provider, "installed", lambda: True)
    calls = []
    def synthesize(*args):
        calls.append(args)
        return b"RIFF0000WAVEdata"
    monkeypatch.setattr(manager._provider, "synthesize", synthesize)
    manager.synthesize("Hello", "en-US")
    manager.synthesize("Hello", "en-US")
    assert len(calls) == 1
    manager.synthesize("Hello", "en-US", rate=1.2)
    manager.synthesize("Hello", "en-US", voice="1")
    manager.synthesize("你好", "zh-CN")
    assert len(calls) == 4
    assert calls[-1][1] == "3"
    assert not any(p.suffix == ".wav" for p in tmp_path.rglob("*"))
    for i in range(40):
        manager.synthesize(f"Sentence {i}")
    assert len(manager._cache) <= 32
    manager.configure(False, "3", "0")
    assert not manager._cache


@pytest.mark.parametrize("kwargs", [{"text": ""}, {"text": "a" * 8001}, {"text": "ok", "language": "fr"}, {"text": "ok", "rate": float("nan")}, {"text": "ok", "rate": True}, {"text": "ok", "rate": 3}])
def test_input_validation(tmp_path, kwargs):
    with pytest.raises(ValueError):
        tts.TTSManager(tmp_path).synthesize(**kwargs)


def test_interrupted_install_is_retryable(tmp_path):
    tts._write_json(tmp_path / "install.json", {"state": "running"})
    (tmp_path / "install.lock").touch()
    assert tts.TTSManager(tmp_path).status()["install"]["state"] == "failed"


def test_resident_worker_returns_wav(tmp_path, monkeypatch):
    import sys
    import wave
    fake = tmp_path / "sherpa_onnx.py"
    fake.write_text('''
class Config:
    def __init__(self, **kwargs): pass
    def validate(self): return True
OfflineTtsConfig = OfflineTtsModelConfig = OfflineTtsKokoroModelConfig = Config
class OfflineTts:
    def __init__(self, config): pass
    def generate(self, text, sid, speed):
        class Audio:
            samples = [0.0, 0.2, -0.2] * 40
            sample_rate = 24000
        return Audio()
''')
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    real_popen = tts.subprocess.Popen
    def fake_runtime(command, **kwargs):
        assert "-I" in command
        return real_popen([part for part in command if part != "-I"], **kwargs)
    monkeypatch.setattr(tts.subprocess, "Popen", fake_runtime)
    provider = tts.KokoroProvider(tmp_path)
    provider.python = Path(sys.executable)
    try:
        audio = provider.synthesize("Hello", "0", 1.0)
        process = provider.process
        assert provider.synthesize("你好", "3", 1.0) == audio
        assert provider.process is process
        with wave.open(io.BytesIO(audio), "rb") as wav:
            assert wav.getframerate() == 24000
            assert wav.getnchannels() == 1
            assert wav.getsampwidth() == 2
    finally:
        provider.close()
    assert process.poll() is not None


def test_model_install_uses_isolated_pinned_runtime(tmp_path, monkeypatch):
    provider = tts.KokoroProvider(tmp_path)
    archive = tmp_path / (tts.MODEL["id"] + ".tar.bz2")
    with tarfile.open(archive, "w:bz2") as tar:
        for name in tts._REQUIRED:
            item = tarfile.TarInfo(tts.MODEL["id"] + "/" + name)
            item.size = 1
            tar.addfile(item, io.BytesIO(b"x"))
        item = tarfile.TarInfo(tts.MODEL["id"] + "/espeak-ng-data")
        item.type = tarfile.DIRTYPE
        tar.addfile(item)
    monkeypatch.setattr(tts, "_download_model", lambda path, cancelled=None: None)
    # Existing interpreter without pip simulates an interrupted ensurepip step.
    provider.python.parent.mkdir(parents=True)
    provider.python.touch()
    commands = []
    monkeypatch.setattr(provider, "_run_install", lambda command, cancelled, timeout: commands.append(command))
    provider.install()
    assert provider.installed()
    assert commands[0][2:4] == ["-m", "venv"]
    command = commands[1]
    assert "--isolated" in command and "--no-deps" in command
    assert "sherpa-onnx==1.12.29" in command
    assert "https://pypi.org/simple" in command
    assert archive.exists()


@pytest.mark.parametrize("action", ["disable", "close"])
def test_slow_synthesis_does_not_block_status_or_cancellation(tmp_path, monkeypatch, action):
    manager = tts.TTSManager(tmp_path)
    manager.configure(True, "3", "0")
    entered, release = threading.Event(), threading.Event()
    errors = []
    monkeypatch.setattr(manager._provider, "installed", lambda: True)

    def slow(*args):
        entered.set()
        assert release.wait(5)
        # A provider may finish successfully just as cancellation arrives.
        return b"RIFF0000WAVEdata"

    monkeypatch.setattr(manager._provider, "synthesize", slow)
    monkeypatch.setattr(manager._provider, "close", release.set)

    def synthesize():
        try:
            manager.synthesize("Hello", "en-US")
        except RuntimeError as error:
            errors.append(str(error))

    thread = threading.Thread(target=synthesize)
    thread.start()
    assert entered.wait(2)
    status_done = threading.Event()
    poller = threading.Thread(target=lambda: (manager.status(), status_done.set()))
    poller.start()
    try:
        assert status_done.wait(1), "Status blocked behind synthesis"
        stopped = threading.Event()
        def stop():
            if action == "disable":
                manager.configure(False, "3", "0")
            else:
                manager.close()
            stopped.set()
        closer = threading.Thread(target=stop)
        closer.start()
        assert stopped.wait(1), "Cancellation blocked behind synthesis"
        thread.join(2)
        closer.join(2)
        assert not thread.is_alive()
        assert errors and "cancelled" in errors[0]
        assert not manager._cache
        if action == "close":
            with pytest.raises(RuntimeError, match="cancelled"):
                manager.synthesize("New request")
    finally:
        release.set()
        thread.join(5)
        poller.join(5)


@pytest.mark.parametrize("action", ["close", "cancel"])
def test_provider_close_interrupts_running_worker(tmp_path, monkeypatch, action):
    import sys
    (tmp_path / "sherpa_onnx.py").write_text('''
import time
class Config:
    def __init__(self, **kwargs): pass
    def validate(self): return True
OfflineTtsConfig = OfflineTtsModelConfig = OfflineTtsKokoroModelConfig = Config
class OfflineTts:
    def __init__(self, config): pass
    def generate(self, text, sid, speed): time.sleep(60)
''')
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    real_popen = tts.subprocess.Popen
    started = threading.Event()
    def fake_runtime(command, **kwargs):
        process = real_popen([p for p in command if p != "-I"], **kwargs)
        started.set()
        return process
    monkeypatch.setattr(tts.subprocess, "Popen", fake_runtime)
    provider = tts.KokoroProvider(tmp_path)
    provider.python = Path(sys.executable)
    errors = []
    cancelled = threading.Event()
    def synthesize():
        try:
            provider.synthesize("Hello", "0", 1.0, cancelled)
        except RuntimeError as error:
            errors.append(str(error))
    thread = threading.Thread(target=synthesize)
    thread.start()
    assert started.wait(2)
    if action == "close":
        provider.close()
    else:
        cancelled.set()
    thread.join(3)
    assert not thread.is_alive()
    assert errors
    assert provider.process is None


def test_close_cancels_installer_before_releasing_lock(tmp_path, monkeypatch):
    manager = tts.TTSManager(tmp_path)
    entered = threading.Event()
    lock_was_held = []
    def install(cancelled):
        entered.set()
        assert cancelled.wait(3)
        lock_was_held.append(tts._acquire_lock(tmp_path / "install.lock") is None)
        raise RuntimeError("cancelled")
    monkeypatch.setattr(manager._provider, "install", install)
    manager.install()
    assert entered.wait(2)
    manager.close()
    assert not manager._install_thread.is_alive()
    assert lock_was_held == [True]
    assert manager.status()["install"]["state"] == "failed"
    assert "cancelled" in manager.status()["install"]["message"]
    handle = tts._acquire_lock(tmp_path / "install.lock")
    assert handle is not None
    handle.close()


def test_install_process_is_terminated_on_cancellation(tmp_path, monkeypatch):
    import sys
    provider = tts.KokoroProvider(tmp_path)
    cancelled, started = threading.Event(), threading.Event()
    real_popen = tts.subprocess.Popen
    children = []
    errors = []
    def launch(*args, **kwargs):
        assert kwargs["env"]["PIP_CONFIG_FILE"] == tts.os.devnull
        child = real_popen(*args, **kwargs)
        children.append(child)
        started.set()
        return child
    monkeypatch.setattr(tts.subprocess, "Popen", launch)
    def install():
        try:
            provider._run_install([sys.executable, "-I", "-c", "import time; time.sleep(60)"], cancelled, 120)
        except RuntimeError as error:
            errors.append(str(error))
    thread = threading.Thread(target=install)
    thread.start()
    assert started.wait(2)
    cancelled.set()
    thread.join(4)
    assert not thread.is_alive()
    assert children[0].poll() is not None
    assert errors == ["Installation cancelled"]
    assert provider._install_process is None


def test_preview_does_not_enable_or_save_and_skips_audio_cache(tmp_path, monkeypatch):
    manager = tts.TTSManager(tmp_path)
    monkeypatch.setattr(manager._provider, "installed", lambda: True)
    calls = []
    monkeypatch.setattr(manager._provider, "synthesize", lambda *args: calls.append(args) or b"RIFF0000WAVEdata")
    assert not (tmp_path / "settings.json").exists()
    manager.preview("Hello", "en-US")
    manager.preview("Hello", "en-US")
    assert len(calls) == 2
    assert not manager._cache
    assert not (tmp_path / "settings.json").exists()
    assert not manager.status()["enabled"]
    with pytest.raises(RuntimeError, match="disabled"):
        manager.synthesize("Hello", "en-US")
    monkeypatch.setattr(manager._provider, "installed", lambda: False)
    with pytest.raises(RuntimeError, match="Install"):
        manager.preview("Hello", "en-US")


def test_models_are_offline_and_candidate_preview_is_isolated(tmp_path, monkeypatch):
    manager = tts.TTSManager(tmp_path / "empty")
    models = manager.models()
    assert len(models) == 5
    assert not manager.root.exists()
    candidate_id = "vits-piper-zh_CN-huayan-medium"
    candidate = manager._providers[candidate_id]
    monkeypatch.setattr(candidate, "installed", lambda: True)
    calls = []
    monkeypatch.setattr(candidate, "synthesize", lambda *args: calls.append(args) or b"RIFF0000WAVEdata")
    manager.preview("你好", model_id=candidate_id)
    assert calls[0][1] == "0"
    assert not manager.status()["installed"]
    assert manager.status()["model"]["id"] == tts.MODEL["id"]
    selected = next(model for model in manager.models() if model["id"] == candidate_id)
    assert selected["installed"]
    assert selected["languages"] == ["zh-CN"]
    assert selected["download_bytes"] == 67255926
    assert "unknown" in selected["license"]
    assert selected["source_url"].startswith("https://github.com/k2-fsa/")
    assert selected["license_url"].endswith("MODEL_CARD")
    with pytest.raises(ValueError, match="language"):
        manager.preview("Hello", "en-US", model_id=candidate_id)
    with pytest.raises(ValueError, match="voice"):
        manager.preview("你好", voice="3", model_id=candidate_id)
    with pytest.raises(ValueError, match="model"):
        manager.preview("你好", model_id="https://arbitrary.invalid/model")


def test_candidate_install_state_and_shared_runtime_lock(tmp_path, monkeypatch):
    manager = tts.TTSManager(tmp_path)
    other = tts.TTSManager(tmp_path)
    candidate_id = "vits-piper-zh_CN-huayan-medium"
    entered, release = threading.Event(), threading.Event()
    def install(cancelled):
        entered.set()
        assert release.wait(3)
    monkeypatch.setattr(manager._providers[candidate_id], "install", install)
    manager.install(candidate_id)
    try:
        assert entered.wait(2)
        assert manager.status()["install"]["state"] == "idle"
        candidate = next(model for model in manager.models() if model["id"] == candidate_id)
        assert candidate["install"]["state"] == "running"
        assert other.install(candidate_id)["install"]["state"] == "running"
        with pytest.raises(RuntimeError, match="Another model"):
            other.install()
    finally:
        release.set()
        manager._install_thread.join(3)
    assert next(model for model in manager.models() if model["id"] == candidate_id)["install"]["state"] == "completed"
    assert manager.status()["install"]["state"] == "idle"


def test_piper_install_reuses_shared_runtime_without_pip(tmp_path, monkeypatch):
    provider = tts.PiperProvider(tmp_path, "vits-piper-zh_CN-huayan-medium")
    archive = tmp_path / (provider.model["id"] + ".tar.bz2")
    with tarfile.open(archive, "w:bz2") as tar:
        for name in provider.required:
            item = tarfile.TarInfo(provider.model["id"] + "/" + name)
            item.size = 1
            tar.addfile(item, io.BytesIO(b"x"))
        item = tarfile.TarInfo(provider.model["id"] + "/espeak-ng-data")
        item.type = tarfile.DIRTYPE
        tar.addfile(item)
    download_specs = []
    monkeypatch.setattr(tts, "_download_model", lambda path, cancelled, model: download_specs.append(model))
    provider.python.parent.mkdir(parents=True)
    provider.python.touch()
    tts._write_json(tmp_path / "runtime.json", {"runtime": tts.RUNTIME_VERSION})
    commands = []
    monkeypatch.setattr(provider, "_run_install", lambda command, cancelled, timeout: commands.append(command))
    provider.install()
    assert provider.installed()
    assert len(commands) == 1
    assert commands[0][-1] == "import sherpa_onnx, numpy"
    assert download_specs[0]["sha256"] == "dbdfec42b91d9cee31cce9ff4b3e9c305eb6fbf60546d071f7e46273554cce6b"
    assert not (tmp_path / "installed.json").exists()


def test_piper_worker_uses_vits_config_and_remains_resident(tmp_path, monkeypatch):
    import sys
    (tmp_path / "sherpa_onnx.py").write_text('''
class Config:
    def __init__(self, **kwargs): self.kwargs = kwargs
    def validate(self): return True
class VitsConfig(Config):
    def __init__(self, **kwargs):
        assert kwargs['model'].endswith('zh_CN-huayan-medium.onnx')
        assert kwargs['data_dir'].endswith('espeak-ng-data')
        super().__init__(**kwargs)
OfflineTtsConfig = OfflineTtsModelConfig = Config
OfflineTtsVitsModelConfig = VitsConfig
class OfflineTts:
    def __init__(self, config):
        assert 'vits' in config.kwargs['model'].kwargs
    def generate(self, text, sid, speed):
        assert sid == 0
        class Audio:
            samples = [0.0, 0.2, -0.2] * 40
            sample_rate = 22050
        return Audio()
''')
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    real_popen = tts.subprocess.Popen
    monkeypatch.setattr(tts.subprocess, "Popen", lambda command, **kwargs: real_popen([p for p in command if p != "-I"], **kwargs))
    provider = tts.PiperProvider(tmp_path, "vits-piper-zh_CN-huayan-medium")
    provider.python = Path(sys.executable)
    try:
        audio = provider.synthesize("你好", "0", 1.0)
        process = provider.process
        assert provider.synthesize("再次试听", "0", 1.0).startswith(b"RIFF")
        assert provider.process is process
        import wave
        with wave.open(io.BytesIO(audio)) as wav:
            assert wav.getframerate() == 22050
    finally:
        provider.close()


def test_request_cancellation_while_queued_does_not_close_other_reader(tmp_path, monkeypatch):
    manager = tts.TTSManager(tmp_path)
    manager.configure(True, "3", "0")
    monkeypatch.setattr(manager._provider, "installed", lambda: True)
    entered, release, cancelled = threading.Event(), threading.Event(), threading.Event()
    calls = []
    def slow(*args):
        calls.append(args[0])
        entered.set()
        assert release.wait(3)
        return b"RIFF0000WAVEdata"
    monkeypatch.setattr(manager._provider, "synthesize", slow)
    other_result = []
    first = threading.Thread(target=lambda: other_result.append(manager.synthesize("Reader A")))
    first.start()
    assert entered.wait(2)
    errors = []
    def queued():
        try:
            manager.synthesize("Reader B", cancel_event=cancelled)
        except RuntimeError as error:
            errors.append(str(error))
    second = threading.Thread(target=queued)
    second.start()
    cancelled.set()
    second.join(1)
    try:
        assert not second.is_alive()
        assert errors == ["Local speech was cancelled"]
        assert calls == ["Reader A"]
        assert manager.status()["enabled"]
    finally:
        release.set()
        first.join(3)
    assert other_result
    assert len(manager._cache) == 1


def test_request_cancel_after_provider_result_never_populates_cache(tmp_path, monkeypatch):
    manager = tts.TTSManager(tmp_path)
    manager.configure(True, "3", "0")
    monkeypatch.setattr(manager._provider, "installed", lambda: True)
    cancelled = threading.Event()
    def synthesize(text, voice, rate, token):
        cancelled.set()
        assert token.is_set()
        return b"RIFF0000WAVEdata"
    monkeypatch.setattr(manager._provider, "synthesize", synthesize)
    with pytest.raises(RuntimeError, match="cancelled"):
        manager.synthesize("Hello", cancel_event=cancelled)
    assert not manager._cache
    assert manager.status()["enabled"]


def test_worker_close_tolerates_broken_pipe_and_repeated_close(tmp_path):
    provider = tts.KokoroProvider(tmp_path)
    class BrokenStream:
        def close(self):
            raise BrokenPipeError("Worker was terminated during request flush")
    class Process:
        stdin = stdout = BrokenStream()
        stops = 0
        def terminate(self):
            self.stops += 1
        def wait(self, timeout=None):
            return -15
    process = Process()
    provider.process = process
    threads = [threading.Thread(target=provider.close) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(2)
        assert not thread.is_alive()
    assert process.stops == 1
    assert provider.process is None


def test_kitten_catalogue_and_preview_are_english_only(tmp_path, monkeypatch):
    manager = tts.TTSManager(tmp_path / "absent")
    candidates = [model for model in manager.models() if model["id"].startswith("kitten-")]
    assert [model["download_bytes"] for model in candidates] == [44665081, 81548122]
    names = ["Bella", "Jasper", "Luna", "Bruno", "Rosie", "Hugo", "Kiki", "Leo"]
    for model in candidates:
        assert model["languages"] == ["en-US"]
        assert [voice["id"] for voice in model["voices"]] == names
        assert model["license"] == "Apache-2.0"
        assert tts.KITTEN_MODELS[model["id"]]["revision"] in model["source_url"]
        assert model["license_url"].endswith("README.md")
    assert not manager.root.exists()
    provider = manager._providers[candidates[0]["id"]]
    monkeypatch.setattr(provider, "installed", lambda: True)
    calls = []
    monkeypatch.setattr(provider, "synthesize", lambda *args: calls.append(args) or b"RIFF0000WAVE")
    manager.preview("Hello", language="en-US", model_id=provider.model["id"])
    assert calls[0][1] == "Bella"
    manager.preview("Hello", language="en-US", voice="Jasper", model_id=provider.model["id"])
    assert calls[1][1] == "Jasper"
    assert not manager.status()["enabled"]
    with pytest.raises(ValueError, match="language"):
        manager.preview("你好", model_id=provider.model["id"])
    with pytest.raises(ValueError, match="voice"):
        manager.preview("Hello", "en-US", voice="0", model_id=provider.model["id"])


def test_kitten_install_pins_assets_and_keeps_sherpa_runtime_untouched(tmp_path, monkeypatch):
    provider = tts.KittenProvider(tmp_path, "kitten-tts-micro-0.8")
    (tmp_path / "runtime.json").write_text('{"runtime":"sherpa-sentinel"}')
    downloads, commands = [], []
    def download(path, url, digest, size, cancelled=None):
        downloads.append((url, digest, size))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"stub")
    monkeypatch.setattr(tts, "_download_asset", download)
    def run(command, cancelled, timeout):
        commands.append(command)
        if "venv" in command:
            provider.python.parent.mkdir(parents=True)
            provider.python.touch()
    monkeypatch.setattr(provider, "_run_install", run)
    provider.install()
    assert provider.installed()
    assert len(downloads) == 5
    assert all(provider.model["revision"] in url for url, _, _ in downloads[:4])
    assert downloads[-1][1] == tts.KITTEN_WHEEL["sha256"]
    assert str(tmp_path / "kitten-venv") in commands[0]
    dependency_install = commands[1]
    assert "misaki==0.9.4" in dependency_install
    assert "phonemizer-fork==3.3.2" in dependency_install
    assert "typer-slim==0.15.4" in dependency_install
    assert "click==8.1.8" in dependency_install
    assert "--no-binary=docopt" in dependency_install
    assert not any("torch" in arg or "misaki[en]" in arg for arg in dependency_install)
    assert "--no-index" in commands[2] and "--no-deps" in commands[2]
    assert commands[3][-1] == tts.KITTEN_IMPORT_CHECK
    assert (tmp_path / "runtime.json").read_text() == '{"runtime":"sherpa-sentinel"}'
    assert not (tmp_path / "venv").exists()
    environment = provider.worker_environment()
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert environment["TRANSFORMERS_OFFLINE"] == "1"
    commands.clear()
    provider.install()
    assert len(commands) == 1, "A second model can reuse the verified Kitten runtime"


def test_verified_asset_download_retries_only_incomplete_files(tmp_path, monkeypatch):
    import hashlib
    payload = b"official-model-bytes"
    digest = hashlib.sha256(payload).hexdigest()
    calls = []
    class Opener:
        def open(self, url, timeout):
            calls.append(url)
            return io.BytesIO(payload)
    monkeypatch.setattr(tts, "build_opener", lambda *_: Opener())
    path = tmp_path / "model.onnx"
    tts._download_asset(path, "https://huggingface.co/KittenML/fixed", digest, len(payload))
    tts._download_asset(path, "https://huggingface.co/KittenML/fixed", digest, len(payload))
    assert len(calls) == 1
    path.write_bytes(b"corrupted")
    tts._download_asset(path, "https://huggingface.co/KittenML/fixed", digest, len(payload))
    assert len(calls) == 2 and path.read_bytes() == payload
    with pytest.raises(ValueError, match="checksum"):
        tts._download_asset(tmp_path / "bad", "https://huggingface.co/KittenML/fixed", "0" * 64, len(payload))
    assert not (tmp_path / "bad").exists()
    assert not (tmp_path / "bad.part").exists()


def test_kitten_worker_uses_local_paths_named_voices_and_quiet_protocol(tmp_path, monkeypatch):
    import json
    import sys
    provider = tts.KittenProvider(tmp_path, "kitten-tts-micro-0.8")
    provider.model_dir.mkdir(parents=True)
    (provider.model_dir / provider.model["file"]).touch()
    (provider.model_dir / "voices.npz").touch()
    (provider.model_dir / "config.json").write_text(json.dumps({
        "model_file": provider.model["file"], "voices": "voices.npz",
        "voice_aliases": {"Bella": "expr-voice-2-f"}, "speed_priors": {},
    }))
    package = tmp_path / "kittentts"
    package.mkdir()
    (package / "__init__.py").write_text('def KittenTTS(*args): raise AssertionError("Network constructor forbidden")\n')
    (package / "onnx_model.py").write_text('''
from pathlib import Path
import os
class KittenTTS_1_Onnx:
    def __init__(self, model_path, voices_path, speed_priors, voice_aliases):
        assert Path(model_path).is_file() and Path(voices_path).is_file()
        assert voice_aliases['Bella'] == 'expr-voice-2-f'
        assert os.environ['HF_HUB_OFFLINE'] == os.environ['TRANSFORMERS_OFFLINE'] == '1'
    def generate(self, text, voice, speed, clean_text):
        assert voice == 'Bella' and clean_text is True
        print('private input: ' + text)
        return [[0.0, 0.2, -0.2], [0.0, 0.1, -0.1]]
''')
    (tmp_path / "numpy.py").write_text('''
class Array:
    def __init__(self, data): self.data = data
    def reshape(self, dimension):
        assert dimension == -1
        return [item for row in self.data for item in row]
def asarray(data): return Array(data)
''')
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    real_popen = tts.subprocess.Popen
    monkeypatch.setattr(tts.subprocess, "Popen", lambda command, **kwargs: real_popen([arg for arg in command if arg != "-I"], **kwargs))
    provider.python = Path(sys.executable)
    try:
        audio = provider.synthesize("Hello", "Bella", 1.0)
        process = provider.process
        assert provider.synthesize("Another request", "Bella", 1.0) == audio
        assert process is provider.process
        import wave
        with wave.open(io.BytesIO(audio)) as wav:
            assert wav.getnframes() == 6 and wav.getframerate() == 24000
    finally:
        provider.close()
    (provider.model_dir / "voices.npz").unlink()
    try:
        with pytest.raises(RuntimeError):
            provider.synthesize("Missing voices", "Bella", 1.0)
    finally:
        provider.close()


def test_legacy_selection_migration_is_read_only(tmp_path):
    tts._write_json(tmp_path / "settings.json", {"enabled": True, "voice_zh": "4", "voice_en": "1", "unrelated": {"keep": True}})
    before = (tmp_path / "settings.json").read_bytes()
    manager = tts.TTSManager(tmp_path)
    status = manager.status()
    assert status["selections"] == {"zh": {"model_id": tts.MODEL["id"], "voice": "4"}, "en": {"model_id": tts.MODEL["id"], "voice": "1"}}
    assert not status["installed"]
    assert len(status["models"]) == 5
    assert (tmp_path / "settings.json").read_bytes() == before
    tts._write_json(tmp_path / "settings.json", {"enabled": False})
    assert manager.status()["selections"] == {"zh": None, "en": None}


def test_independent_language_selections_preserve_unrelated_settings(tmp_path, monkeypatch):
    manager = tts.TTSManager(tmp_path)
    tts._write_json(tmp_path / "settings.json", {"voice_zh": "4", "voice_en": "1", "unrelated": {"keep": True}})
    zh = "vits-piper-zh_CN-huayan-medium"
    en = "kitten-tts-micro-0.8"
    for model in (zh, en):
        monkeypatch.setattr(manager._providers[model], "installed", lambda: True)
    selections = {"zh": {"model_id": zh, "voice": "0"}, "en": {"model_id": en, "voice": "Jasper"}}
    status = manager.configure(selections=selections)
    assert status["selections"] == selections and status["enabled"]
    assert status["voice_zh"] == "4" and status["voice_en"] == "1"
    assert tts._read_json(tmp_path / "settings.json")["unrelated"] == {"keep": True}
    status = manager.configure(selections={"zh": None, "en": selections["en"]})
    assert status["selections"]["zh"] is None and status["enabled"]
    status = manager.configure(selections={"zh": None, "en": None})
    assert not status["enabled"]
    manager.configure(True, "3", "2")
    assert manager.status()["selections"]["en"] == {"model_id": tts.MODEL["id"], "voice": "2"}
    assert tts._read_json(tmp_path / "settings.json")["unrelated"] == {"keep": True}


@pytest.mark.parametrize("selections", [
    {}, {"zh": None}, {"zh": None, "en": None, "fr": None},
    {"zh": None, "en": {"model_id": "unknown", "voice": "0"}},
    {"zh": {"model_id": "kitten-tts-mini-0.8", "voice": "Bella"}, "en": None},
    {"zh": None, "en": {"model_id": "kitten-tts-mini-0.8", "voice": "0"}},
    {"zh": None, "en": {"model_id": "kitten-tts-mini-0.8", "voice": "Bella", "url": "bad"}},
    {"zh": None, "en": {"model_id": None, "voice": "0"}},
])
def test_invalid_selections_never_mutate_settings(tmp_path, monkeypatch, selections):
    manager = tts.TTSManager(tmp_path)
    for provider in manager._providers.values():
        monkeypatch.setattr(provider, "installed", lambda: True)
    with pytest.raises(ValueError):
        manager.configure(selections=selections)
    assert not (tmp_path / "settings.json").exists()


def test_selection_requires_install_but_explicit_speech_ignores_legacy_enabled(tmp_path, monkeypatch):
    manager = tts.TTSManager(tmp_path)
    model_id = "kitten-tts-mini-0.8"
    choice = {"zh": None, "en": {"model_id": model_id, "voice": "Leo"}}
    with pytest.raises(ValueError, match="Install"):
        manager.configure(selections=choice)
    with pytest.raises(RuntimeError, match="Install"):
        manager.synthesize("Hello", "en-US", voice="Leo", model_id=model_id)
    provider = manager._providers[model_id]
    monkeypatch.setattr(provider, "installed", lambda: True)
    calls = []
    monkeypatch.setattr(provider, "synthesize", lambda *args: calls.append(args) or b"RIFF0000WAVE")
    manager.synthesize("Hello", "en-US", voice="Leo", model_id=model_id)
    assert calls[0][1] == "Leo"
    assert not manager.status()["enabled"]
    with pytest.raises(RuntimeError, match="disabled"):
        manager.synthesize("Hello", "en-US")
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(RuntimeError, match="cancelled"):
        manager.synthesize("Cancelled", "en-US", voice="Leo", model_id=model_id, cancel_event=cancelled)
    assert len(calls) == 1


def test_saving_system_defaults_does_not_cancel_explicit_reader(tmp_path, monkeypatch):
    manager = tts.TTSManager(tmp_path)
    model_id = "kitten-tts-micro-0.8"
    provider = manager._providers[model_id]
    monkeypatch.setattr(provider, "installed", lambda: True)
    entered, release = threading.Event(), threading.Event()
    tokens, results, errors = [], [], []
    closed = []
    monkeypatch.setattr(provider, "close", lambda: closed.append(True))
    def synthesize(text, voice, rate, token):
        tokens.append(token)
        entered.set()
        assert release.wait(3)
        assert not token.is_set()
        return b"RIFF0000WAVE"
    monkeypatch.setattr(provider, "synthesize", synthesize)
    def read():
        try:
            results.append(manager.synthesize("Reader A", "en-US", "Bella", model_id=model_id))
        except Exception as error:
            errors.append(error)
    reader = threading.Thread(target=read)
    reader.start()
    assert entered.wait(2)
    try:
        status = manager.configure(selections={"zh": None, "en": None})
        assert not status["enabled"]
        assert not tokens[0].is_set()
        assert not closed
    finally:
        release.set()
        reader.join(3)
    assert results and not errors
    assert manager.synthesize("Reader B", "en-US", "Bella", model_id=model_id) == results[0]


def test_cancelled_preview_releases_synthesis_slot_for_other_reader(tmp_path, monkeypatch):
    import time
    manager = tts.TTSManager(tmp_path)
    model_id = "kitten-tts-micro-0.8"
    provider = manager._providers[model_id]
    monkeypatch.setattr(provider, "installed", lambda: True)
    entered, cancelled = threading.Event(), threading.Event()
    errors = []
    def generate(text, voice, rate, token):
        if text == "cancel preview":
            entered.set()
            deadline = time.monotonic() + 2
            while not token.is_set() and time.monotonic() < deadline:
                time.sleep(0.005)
            assert token.is_set()
            raise RuntimeError("Cancelled preview")
        assert not token.is_set()
        return b"RIFF0000WAVE"
    monkeypatch.setattr(provider, "synthesize", generate)
    def preview():
        try:
            manager.preview("cancel preview", "en-US", model_id=model_id, cancel_event=cancelled)
        except RuntimeError as error:
            errors.append(str(error))
    thread = threading.Thread(target=preview)
    thread.start()
    assert entered.wait(1)
    cancelled.set()
    assert manager.synthesize("other reader", "en-US", model_id=model_id) == b"RIFF0000WAVE"
    thread.join(1)
    assert not thread.is_alive()
    assert errors == ["Cancelled preview"]
    assert len(manager._cache) == 1
    assert not manager._closed
