"""Opt-in, isolated local speech synthesis. No network work occurs on import/status."""
from __future__ import annotations

import base64
from collections import OrderedDict
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import queue
import shutil
import signal
import subprocess
import tarfile
import tempfile
import time
import sys
import threading
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, build_opener

MODEL = {
    "id": "kokoro-int8-multi-lang-v1_1",
    "name": "Kokoro Chinese + English v1.1 INT8",
    "license": "Apache-2.0",
    "download_bytes": 147031220,
}
# GitHub release asset metadata, verified against the tts-models release.
MODEL_SHA256 = "a1e94694776049035c4f2c6529f003aaece993c76aae9a78995831c3c4dcafc6"
MODEL_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/" + MODEL["id"] + ".tar.bz2"
RUNTIME_VERSION = "1.12.29"
MAX_TEXT_LENGTH = 8000
VOICES = [
    {"id": "0", "name": "af_maple", "language": "en-US"},
    {"id": "1", "name": "af_sol", "language": "en-US"},
    {"id": "2", "name": "bf_vale", "language": "en-GB"},
] + [
    {"id": str(i), "name": f"中文{'女' if i < 58 else '男'}声 {i}", "language": "zh-CN"}
    for i in range(3, 103)
]
_REQUIRED = ("model.int8.onnx", "voices.bin", "tokens.txt", "lexicon-us-en.txt", "lexicon-zh.txt", "number-zh.fst", "date-zh.fst", "phone-zh.fst", "LICENSE")

# SHA256 values are from the official tts-models/checksum.txt release asset.
PIPER_MODELS = {
    "vits-piper-zh_CN-huayan-medium": {
        "id": "vits-piper-zh_CN-huayan-medium", "name": "Piper 华雁中文 medium",
        "license": "Dataset license unknown (see MODEL_CARD)", "download_bytes": 67255926,
        "sha256": "dbdfec42b91d9cee31cce9ff4b3e9c305eb6fbf60546d071f7e46273554cce6b",
        "file": "zh_CN-huayan-medium.onnx", "languages": ["zh-CN"],
        "voices": [{"id": "0", "name": "华雁", "language": "zh-CN"}],
    },
    "vits-piper-en_US-lessac-medium": {
        "id": "vits-piper-en_US-lessac-medium", "name": "Piper Lessac English medium",
        "license": "Blizzard 2013 Lessac dataset terms (see MODEL_CARD)", "download_bytes": 67230653,
        "sha256": "9e3febfacf0abf4270172d2958bcec246032b7e88efc2720840cc80c93de334e",
        "file": "en_US-lessac-medium.onnx", "languages": ["en-US"],
        "voices": [{"id": "0", "name": "Lessac", "language": "en-US"}],
    },
}


KITTEN_RUNTIME_VERSION = "0.8.1"
KITTEN_WHEEL = {
    "name": "kittentts-0.8.1-py3-none-any.whl", "size": 22210,
    "url": "https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl",
    "sha256": "482a436c4f1f3192153710376e459ff3689517ebcda7c2b051e2fd4187b41851",
}
# The ONNX path imports misaki.en but never creates its Transformer-backed G2P.
# Do not install misaki[en] or the conflicting standard phonemizer distribution.
KITTEN_REQUIREMENTS = (
    "numpy==2.2.6", "onnxruntime==1.23.2", "soundfile==0.13.1",
    "huggingface-hub==0.36.0", "misaki==0.9.4", "phonemizer-fork==3.3.2",
    "espeakng-loader==0.2.4", "spacy==3.8.11", "num2words==0.5.14",
    "typer-slim==0.15.4", "click==8.1.8", "docopt==0.6.2",
)
KITTEN_VOICES = [{"id": name, "name": name, "language": "en-US"} for name in
                 ("Bella", "Jasper", "Luna", "Bruno", "Rosie", "Hugo", "Kiki", "Leo")]
# LFS SHA256 values and revisions come from the official KittenML HF repositories.
# Small-file SHA256 values were calculated from those exact revisions.
KITTEN_MODELS = {
    "kitten-tts-micro-0.8": {
        "id": "kitten-tts-micro-0.8", "name": "KittenTTS Micro 40M (0.8)",
        "revision": "1ccf72b2c2048fd17efac7de2fab32d10e225084",
        "files": {
            "kitten_tts_micro_v0_8.onnx": (41384970, "95481626fee1ba70ce683e69c534fc7cb38433c46ce42d3abbeafb4b9f1a4123"),
            "voices.npz": (3278902, "112710c1be8ad0e967c190fb0fd95cbe5848ec4791b93209f20b28b7da20dac1"),
            "config.json": (473, "1f0bd2208348f9211cb0da64fcd1536eb28228571cc6b09e767eb6e203a0a532"),
            "README.md": (736, "bdee9c78ef3877a7993dceff93394ce3d58117c32768114da6a055a90e5b2905"),
        },
    },
    "kitten-tts-mini-0.8": {
        "id": "kitten-tts-mini-0.8", "name": "KittenTTS Mini 80M (0.8)",
        "revision": "c02725660cea441db4c383af69f1f26f5cd00947",
        "files": {
            "kitten_tts_mini_v0_8.onnx": (78268016, "0f5bbae4fc4800c98dbc544a87ecfa79510de2fb8222db30d12e5bfe9177df91"),
            "voices.npz": (3278902, "40ad2638952b77b7b2f30127e2608e169fc69dd256b53bd8aaa3409a33193c42"),
            "config.json": (470, "6b160bc9b19e24ecb21e84bc14f8a7da21fdf47ec72d42450bc5cf514b61804a"),
            "README.md": (734, "cab0af19aa75f409684d165407c32a0d845cc8fc660606c379f4b0663f87abae"),
        },
    },
}
KITTEN_IMPORT_CHECK = (
    "from importlib.metadata import version; "
    "assert version('kittentts') == '0.8.1'; "
    "from kittentts.onnx_model import KittenTTS_1_Onnx; "
    "from phonemizer.backend import EspeakBackend; "
    "assert EspeakBackend(language='en-us').phonemize(['Hello'])[0]"
)


class _CancellationToken:
    def __init__(self, *events):
        self.events = tuple(event for event in events if event is not None)

    def is_set(self):
        return any(event.is_set() for event in self.events)


@contextmanager
def _synthesis_slot(lock, cancelled):
    while True:
        if cancelled.is_set():
            raise RuntimeError("Local speech was cancelled")
        if lock.acquire(timeout=0.1):
            break
    try:
        yield
    finally:
        lock.release()


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".tts-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _acquire_lock(path: Path):
    handle = path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            handle.write(b"0")
            handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle
    except OSError:
        handle.close()
        return None


def _safe_extract(archive: Path, destination: Path, cancelled=None) -> None:
    """Only regular files/directories, bounded expansion, within an empty stage."""
    total = 0
    with tarfile.open(archive, "r:bz2") as tar:
        for index, item in enumerate(tar):
            _check_cancelled(cancelled)
            name = PurePosixPath(item.name)
            total += item.size
            if (name.is_absolute() or ".." in name.parts or "\\" in item.name
                    or ":" in item.name or not (item.isfile() or item.isdir())
                    or total > 1_000_000_000 or index > 20000):
                raise ValueError("Unsafe model archive")
            target = destination.joinpath(*name.parts)
            if not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError("Unsafe model archive")
            if item.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(item) as source, target.open("wb") as output:
                    while chunk := source.read(1024 * 1024):
                        _check_cancelled(cancelled)
                        output.write(chunk)


class _OfficialRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if parsed.scheme != "https" or parsed.hostname not in {
            "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com",
            "huggingface.co", "cdn-lfs.huggingface.co", "cdn-lfs-us-1.hf.co",
            "cas-bridge.xethub.hf.co", "us.aws.cdn.hf.co",
        }:
            raise ValueError("Unexpected model download host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _check_cancelled(cancelled) -> None:
    if cancelled is not None and cancelled.is_set():
        raise RuntimeError("Installation cancelled")


def _download_model(path: Path, cancelled=None, model=None) -> None:
    _check_cancelled(cancelled)
    digest_expected = model["sha256"] if model is not None else MODEL_SHA256
    size_expected = model["download_bytes"] if model is not None else MODEL["download_bytes"]
    url = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/" + model["id"] + ".tar.bz2") if model is not None else MODEL_URL
    _download_asset(path, url, digest_expected, size_expected, cancelled)


def _download_asset(path, url, digest_expected, size_expected, cancelled=None):
    _check_cancelled(cancelled)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_file():
        with path.open("rb") as f:
            if hashlib.file_digest(f, "sha256").hexdigest() == digest_expected:
                return
    partial = path.with_suffix(".part")
    digest = hashlib.sha256()
    count = 0
    try:
        with build_opener(_OfficialRedirects()).open(url, timeout=5) as response, partial.open("wb") as output:
            while chunk := response.read1(64 * 1024):
                _check_cancelled(cancelled)
                count += len(chunk)
                if count > size_expected:
                    raise ValueError("Model download exceeds expected size")
                digest.update(chunk)
                output.write(chunk)
        if count != size_expected or digest.hexdigest() != digest_expected:
            raise ValueError("Model checksum mismatch")
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)


class KokoroProvider:
    """Provider boundary: installation and resident synthesis process."""
    def __init__(self, root: Path):
        self.root = root
        self.model = dict(MODEL, sha256=MODEL_SHA256, file="model.int8.onnx", languages=["zh-CN", "en-US", "en-GB"], voices=VOICES)
        self.kind = "kokoro"
        self.required = _REQUIRED
        self.model_dir = root / "models" / self.model["id"]
        self.python = root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        self.process = None
        self.responses = None
        self._process_lock = threading.RLock()
        self._install_process = None

    @property
    def marker(self) -> Path:
        return self.root / ("installed.json" if self.kind == "kokoro" else "state/" + self.model["id"] + ".installed.json")

    @property
    def install_state(self) -> Path:
        return self.root / ("install.json" if self.kind == "kokoro" else "state/" + self.model["id"] + ".install.json")

    def installed(self) -> bool:
        marker = _read_json(self.marker)
        return (marker.get("sha256") == self.model["sha256"]
                and marker.get("runtime") == RUNTIME_VERSION and self.python.is_file()
                and all((self.model_dir / p).is_file() for p in self.required)
                and (self.model_dir / "espeak-ng-data").is_dir())

    def install(self, cancelled=None) -> None:
        _check_cancelled(cancelled)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        archive = self.root / (self.model["id"] + ".tar.bz2")
        if self.kind == "kokoro":
            _download_model(archive, cancelled)
        else:
            _download_model(archive, cancelled, self.model)
        self.model_dir.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".extract-", dir=self.root) as stage:
            _safe_extract(archive, Path(stage), cancelled)
            source = Path(stage) / self.model["id"]
            if not all((source / p).is_file() for p in self.required) or not (source / "espeak-ng-data").is_dir():
                raise ValueError("Incomplete model archive")
            if self.model_dir.exists():
                shutil.rmtree(self.model_dir)
            shutil.move(str(source), self.model_dir)
        runtime_ready = _read_json(self.root / "runtime.json").get("runtime") == RUNTIME_VERSION and self.python.is_file()
        if runtime_ready:
            try:
                self._run_install([str(self.python), "-I", "-c", "import sherpa_onnx, numpy"], cancelled, 60)
            except RuntimeError:
                _check_cancelled(cancelled)
                runtime_ready = False
        if not runtime_ready:
            # Re-run ensurepip on retries, including a partially created environment.
            self._run_install([sys.executable, "-I", "-m", "venv", str(self.root / "venv")], cancelled, 120)
            self._run_install([
                str(self.python), "-I", "-m", "pip", "--isolated", "install", "--index-url", "https://pypi.org/simple",
                "--only-binary=:all:", "--disable-pip-version-check", "--no-deps",
                f"sherpa-onnx=={RUNTIME_VERSION}", f"sherpa-onnx-core=={RUNTIME_VERSION}", "numpy==2.2.6",
            ], cancelled, 900)
            self._run_install([str(self.python), "-I", "-c", "import sherpa_onnx, numpy"], cancelled, 60)
            _check_cancelled(cancelled)
            _write_json(self.root / "runtime.json", {"runtime": RUNTIME_VERSION})
        _check_cancelled(cancelled)
        _write_json(self.marker, {"sha256": self.model["sha256"], "runtime": RUNTIME_VERSION})

    def worker_environment(self):
        return dict(os.environ)

    def _run_install(self, command, cancelled, timeout):
        with self._process_lock:
            _check_cancelled(cancelled)
            process = subprocess.Popen(
                command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=(os.name != "nt"),
                env={**{k: v for k, v in self.worker_environment().items() if not k.startswith("PIP_")}, "PIP_CONFIG_FILE": os.devnull},
            )
            self._install_process = process
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                _check_cancelled(cancelled)
                if time.monotonic() > deadline:
                    raise RuntimeError("Installation command timed out")
                try:
                    process.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    pass
            _check_cancelled(cancelled)
            if process.returncode:
                raise RuntimeError("Installation command failed")
        finally:
            if process.poll() is None:
                if os.name != "nt":
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                else:
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    if os.name != "nt":
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    else:
                        process.kill()
                    process.wait()
                if os.name != "nt":
                    # Reap descendants even if the venv/pip parent exited first.
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            with self._process_lock:
                if self._install_process is process:
                    self._install_process = None

    def synthesize(self, text: str, voice: str, rate: float, cancelled=None) -> bytes:
        with self._process_lock:
            if cancelled is not None and cancelled.is_set():
                raise RuntimeError("Local speech was cancelled")
            if self.process is None or self.process.poll() is not None:
                self.process = subprocess.Popen(
                    [str(self.python), "-I", "-u", str(Path(__file__).with_name("tts_worker.py")), str(self.model_dir), self.kind, self.model["file"]],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, encoding="utf-8", bufsize=1, env=self.worker_environment(),
                )
                self.responses = queue.Queue()
                process, responses = self.process, self.responses

                def read_responses():
                    try:
                        for line in process.stdout:
                            responses.put(line)
                    finally:
                        responses.put(None)
                threading.Thread(target=read_responses, daemon=True).start()
            process, responses = self.process, self.responses
        try:
            def send_request():
                try:
                    process.stdin.write(json.dumps({"text": text, "voice": voice if self.kind == "kitten" else int(voice), "rate": rate}, ensure_ascii=False) + "\n")
                    process.stdin.flush()
                except (OSError, ValueError):
                    responses.put(None)
            threading.Thread(target=send_request, daemon=True).start()
            deadline = time.monotonic() + 180
            while True:
                if cancelled is not None and cancelled.is_set():
                    raise RuntimeError("Local speech was cancelled")
                if time.monotonic() > deadline:
                    raise RuntimeError("Local speech synthesis timed out")
                try:
                    response = responses.get(timeout=0.1)
                    break
                except queue.Empty:
                    pass
            if cancelled is not None and cancelled.is_set():
                raise RuntimeError("Local speech was cancelled")
            data = json.loads(response) if response else {}
            audio = base64.b64decode(data.get("audio", ""), validate=True)
            if not audio.startswith(b"RIFF") or audio[8:12] != b"WAVE":
                raise ValueError("Invalid speech response")
            return audio
        except Exception:
            with self._process_lock:
                if self.process is process:
                    self.process = None
                    self._stop(process)
            raise RuntimeError("Local speech synthesis failed or was cancelled") from None

    @staticmethod
    def _stop(process) -> None:
        try:
            process.terminate()
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        for stream in (process.stdin, process.stdout):
            if stream:
                try:
                    stream.close()
                except (OSError, ValueError):
                    # The writer can still flush a request while cancellation kills its pipe.
                    pass

    def close(self) -> None:
        with self._process_lock:
            process, self.process = self.process, None
        if process is not None:
            self._stop(process)


class PiperProvider(KokoroProvider):
    """Fixed Piper/VITS candidates sharing the same isolated sherpa runtime."""
    def __init__(self, root: Path, model_id: str):
        super().__init__(root)
        self.model = dict(PIPER_MODELS[model_id])
        self.kind = "vits"
        self.required = (self.model["file"], "tokens.txt", "MODEL_CARD")
        self.model_dir = root / "models" / self.model["id"]


class KittenProvider(KokoroProvider):
    """Pinned official Kitten ONNX assets, with a separate optional runtime."""
    def __init__(self, root: Path, model_id: str):
        super().__init__(root)
        spec = KITTEN_MODELS[model_id]
        model_file = next(name for name in spec["files"] if name.endswith(".onnx"))
        self.model = dict(spec, license="Apache-2.0", languages=["en-US"], voices=KITTEN_VOICES,
                          file=model_file, sha256=spec["files"][model_file][1],
                          download_bytes=sum(value[0] for value in spec["files"].values()))
        self.kind = "kitten"
        self.required = tuple(spec["files"])
        self.model_dir = root / "models" / model_id
        self.python = root / "kitten-venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        self.runtime_identity = hashlib.sha256(json.dumps([KITTEN_WHEEL["sha256"], KITTEN_REQUIREMENTS]).encode()).hexdigest()

    def worker_environment(self):
        return {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                "HF_DATASETS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1"}

    def installed(self) -> bool:
        marker = _read_json(self.marker)
        return (marker.get("runtime") == self.runtime_identity and self.python.is_file()
                and marker.get("revision") == self.model["revision"]
                and all((self.model_dir / name).is_file() for name in self.required))

    def install(self, cancelled=None) -> None:
        _check_cancelled(cancelled)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for name, (size, digest) in self.model["files"].items():
            url = "https://huggingface.co/KittenML/" + self.model["id"] + "/resolve/" + self.model["revision"] + "/" + name
            _download_asset(self.model_dir / name, url, digest, size, cancelled)
        wheel = self.root / "downloads" / KITTEN_WHEEL["name"]
        _download_asset(wheel, KITTEN_WHEEL["url"], KITTEN_WHEEL["sha256"], KITTEN_WHEEL["size"], cancelled)
        runtime_marker = self.root / "kitten-runtime.json"
        ready = _read_json(runtime_marker).get("runtime") == self.runtime_identity and self.python.is_file()
        if ready:
            try:
                self._run_install([str(self.python), "-I", "-c", KITTEN_IMPORT_CHECK], cancelled, 90)
            except RuntimeError:
                _check_cancelled(cancelled)
                ready = False
        if not ready:
            self._run_install([sys.executable, "-I", "-m", "venv", str(self.root / "kitten-venv")], cancelled, 120)
            # docopt 0.6.2 publishes an sdist only; no other source builds are permitted.
            self._run_install([
                str(self.python), "-I", "-m", "pip", "--isolated", "install", "--index-url", "https://pypi.org/simple",
                "--only-binary=:all:", "--no-binary=docopt", "--disable-pip-version-check", *KITTEN_REQUIREMENTS,
            ], cancelled, 900)
            self._run_install([
                str(self.python), "-I", "-m", "pip", "--isolated", "install", "--no-deps", "--no-index", str(wheel),
            ], cancelled, 120)
            self._run_install([str(self.python), "-I", "-c", KITTEN_IMPORT_CHECK], cancelled, 90)
            _check_cancelled(cancelled)
            _write_json(runtime_marker, {"runtime": self.runtime_identity})
        _check_cancelled(cancelled)
        _write_json(self.marker, {"runtime": self.runtime_identity, "revision": self.model["revision"]})


class TTSManager:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root is not None else Path(os.environ.get("ALC_TTS_DIR", "~/.alc/tts")).expanduser()
        self._provider = KokoroProvider(self.root)
        self._providers = {MODEL["id"]: self._provider,
                           **{key: PiperProvider(self.root, key) for key in PIPER_MODELS},
                           **{key: KittenProvider(self.root, key) for key in KITTEN_MODELS}}
        self._lock = threading.RLock()
        self._synthesis_lock = threading.Lock()
        self._generation = threading.Event()
        self._closed = False
        self._install_thread = None
        self._install_cancelled = threading.Event()
        self._cache = OrderedDict()
        self._cache_bytes = 0

    def status(self) -> dict:
        with self._lock:
            config = _read_json(self.root / "settings.json")
            installed = self._provider.installed()
            state = self._state(self._provider, installed)
            return {
                "enabled": config.get("enabled") is True, "installed": installed,
                "install": {"state": state.get("state", "completed" if installed else "idle"), "message": state.get("message", "")},
                "model": dict(MODEL), "voice_zh": config.get("voice_zh", "3"),
                "voice_en": config.get("voice_en", "0"), "voices": [dict(v) for v in VOICES],
                "models": self.models(), "selections": self._selections(config),
            }

    def _state(self, provider, installed):
        state = _read_json(provider.install_state)
        if state.get("state") == "running" and (self.root / "install.lock").exists():
            active = _read_json(self.root / "active-install.json").get("model_id", MODEL["id"])
            handle = _acquire_lock(self.root / "install.lock")
            interrupted = active != provider.model["id"] or handle is not None
            if handle is not None:
                handle.close()
            if interrupted:
                state = {"state": "failed", "message": "Installation was interrupted; retry installation"}
        return {"state": state.get("state", "completed" if installed else "idle"), "message": state.get("message", "")}

    def _get_provider(self, model_id):
        key = MODEL["id"] if model_id is None else model_id
        if not isinstance(key, str) or key not in self._providers:
            raise ValueError("Unsupported local speech model")
        return self._providers[key]

    def _model_status(self, provider):
        installed = provider.installed()
        result = {key: provider.model[key] for key in ("id", "name", "license", "download_bytes")}
        result["source_url"] = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/" + provider.model["id"] + ".tar.bz2"
        result["license_url"] = "https://huggingface.co/csukuangfj/" + provider.model["id"] + "/blob/main/" + ("LICENSE" if provider.kind == "kokoro" else "MODEL_CARD")
        if provider.kind == "kitten":
            result["source_url"] = "https://huggingface.co/KittenML/" + provider.model["id"] + "/tree/" + provider.model["revision"]
            result["license_url"] = "https://huggingface.co/KittenML/" + provider.model["id"] + "/blob/" + provider.model["revision"] + "/README.md"
        result.update(installed=installed, install=self._state(provider, installed),
                      voices=[dict(voice) for voice in provider.model["voices"]], languages=list(provider.model["languages"]))
        return result

    def models(self) -> list[dict]:
        with self._lock:
            return [self._model_status(provider) for provider in self._providers.values()]

    @staticmethod
    def _selections(config):
        if isinstance(config.get("selections"), dict):
            return {language: dict(value) if isinstance(value, dict) else None
                    for language in ("zh", "en") for value in [config["selections"].get(language)]}
        return {language: {"model_id": MODEL["id"], "voice": config.get("voice_" + language, default)}
                if config.get("enabled") is True else None
                for language, default in (("zh", "3"), ("en", "0"))}

    def _validated_selections(self, selections):
        if not isinstance(selections, dict) or set(selections) != {"zh", "en"}:
            raise ValueError("Selections must include exactly zh and en")
        result = {}
        for language, value in selections.items():
            if value is None:
                result[language] = None
                continue
            if not isinstance(value, dict) or set(value) != {"model_id", "voice"}:
                raise ValueError("Each local selection needs model_id and voice")
            provider = self._get_provider(value["model_id"])
            if not isinstance(value["model_id"], str) or not isinstance(value["voice"], str):
                raise ValueError("Model and voice identifiers must be strings")
            if not provider.installed():
                raise ValueError("Install the selected model before choosing its voice")
            if not any(item.split("-")[0] == language for item in provider.model["languages"]):
                raise ValueError("Selected model does not support this language")
            if not any(voice["id"] == value["voice"] and voice["language"].split("-")[0] == language
                       for voice in provider.model["voices"]):
                raise ValueError("Selected voice does not support this language")
            result[language] = dict(value)
        return result

    def configure(self, enabled: bool = False, voice_zh: str = "3", voice_en: str = "0", selections: dict | None = None) -> dict:
        with self._lock:
            if self._closed:
                raise RuntimeError("Local speech manager is closed")
            config = _read_json(self.root / "settings.json")
            if selections is not None:
                selected = self._validated_selections(selections)
                config["selections"] = selected
                enabled = any(value is not None for value in selected.values())
                config["enabled"] = enabled
                for language, value in selected.items():
                    if value is not None and value["model_id"] == MODEL["id"]:
                        config["voice_" + language] = value["voice"]
                config.setdefault("voice_zh", "3")
                config.setdefault("voice_en", "0")
            else:
                if not isinstance(enabled, bool):
                    raise ValueError("enabled must be boolean")
                for voice, language in ((voice_zh, "zh"), (voice_en, "en")):
                    if not any(v["id"] == voice and v["language"].startswith(language) for v in VOICES):
                        raise ValueError("Unsupported voice")
                config.update(enabled=enabled, voice_zh=voice_zh, voice_en=voice_en)
                config.pop("selections", None)
            _write_json(self.root / "settings.json", config)
            if selections is None and not enabled:
                self._generation.set()
                self._generation = threading.Event()
                self._cache.clear()
                self._cache_bytes = 0
        if selections is None and not enabled:
            for provider in self._providers.values():
                provider.close()
        return self.status()

    def install(self, model_id: str | None = None) -> dict:
        provider = self._get_provider(model_id)
        def result():
            return self.status() if model_id is None else self._model_status(provider)
        with self._lock:
            if self._closed:
                raise RuntimeError("Local speech manager is closed")
            if provider.installed():
                return result()
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            handle = _acquire_lock(self.root / "install.lock")
            if handle is None:
                active = _read_json(self.root / "active-install.json").get("model_id", MODEL["id"])
                if active != provider.model["id"]:
                    raise RuntimeError("Another model installation is running; retry after it finishes")
                state = result()
                state["install"] = {"state": "running", "message": "Installation is already running"}
                return state
            _write_json(self.root / "active-install.json", {"model_id": provider.model["id"]})
            _write_json(provider.install_state, {"state": "running", "message": "Installing local speech runtime and model"})
            self._install_cancelled = threading.Event()
            cancelled = self._install_cancelled

            def run():
                try:
                    provider.install(cancelled)
                    _check_cancelled(cancelled)
                    state = {"state": "completed", "message": "Local speech is installed"}
                except Exception:
                    # Exception text from pip/network may contain environment credentials.
                    state = {"state": "failed", "message": ("Installation cancelled; retry installation" if cancelled.is_set() else "Installation failed. Check network, disk space and Python compatibility, then retry.")}
                finally:
                    try:
                        _write_json(provider.install_state, state)
                    finally:
                        handle.close()
            self._install_thread = threading.Thread(target=run, daemon=False, name="alc-tts-install")
            self._install_thread.start()
            return result()

    def synthesize(self, text: str, language: str = "zh-CN", voice: str | None = None, rate: float = 1.0, cancel_event: threading.Event | None = None, model_id: str | None = None) -> bytes:
        return self._synthesize(text, language, voice, rate, model_id, preview=False, cancel_event=cancel_event)

    def preview(self, text: str, language: str = "zh-CN", voice: str | None = None, rate: float = 1.0, model_id: str | None = None, cancel_event: threading.Event | None = None) -> bytes:
        """Audition an installed model without changing production speech settings."""
        return self._synthesize(text, language, voice, rate, model_id, preview=True, cancel_event=cancel_event)

    def _synthesize(self, text, language, voice, rate, model_id, *, preview, cancel_event=None):
        provider = self._get_provider(model_id)
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_LENGTH:
            raise ValueError(f"Speech text must contain 1–{MAX_TEXT_LENGTH} characters")
        if language not in {"zh", "zh-CN", "zh-TW", "en", "en-US", "en-GB"}:
            raise ValueError("Unsupported language")
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or not 0.5 <= rate <= 2.0:
            raise ValueError("Speech rate must be between 0.5 and 2.0")
        with self._lock:
            generation = _CancellationToken(self._generation, cancel_event)
        with _synthesis_slot(self._synthesis_lock, generation):
            with self._lock:
                if self._closed or generation.is_set():
                    raise RuntimeError("Local speech was cancelled")
                status = self.status()
                if not preview and model_id is None and not status["enabled"]:
                    raise RuntimeError("Local speech is disabled")
                if not provider.installed():
                    raise RuntimeError("Install local speech first")
                if not any(item.split("-")[0] == language.split("-")[0] for item in provider.model["languages"]):
                    raise ValueError("Selected model does not support this language")
                default_voice = status["voice_zh" if language.startswith("zh") else "voice_en"] if provider.kind == "kokoro" else provider.model["voices"][0]["id"]
                selected = voice if voice is not None else default_voice
                if not any(v["id"] == selected for v in provider.model["voices"]):
                    raise ValueError("Unsupported voice")
                key = hashlib.sha256(json.dumps([provider.model["id"], provider.model["sha256"], RUNTIME_VERSION, text, language, selected, float(rate)], ensure_ascii=False).encode()).hexdigest()
                if not preview and key in self._cache:
                    self._cache.move_to_end(key)
                    return self._cache[key]
            audio = provider.synthesize(text, selected, float(rate), generation)
            with self._lock:
                if self._closed or generation.is_set():
                    raise RuntimeError("Local speech was cancelled")
                if preview:
                    return audio
                self._cache[key] = audio
                self._cache_bytes += len(audio)
                while self._cache_bytes > 32 * 1024 * 1024 or len(self._cache) > 32:
                    _, removed = self._cache.popitem(last=False)
                    self._cache_bytes -= len(removed)
                return audio

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._install_cancelled.set()
            self._generation.set()
            self._cache.clear()
            self._cache_bytes = 0
        for provider in self._providers.values():
            provider.close()
        if self._install_thread is not None and self._install_thread is not threading.current_thread():
            self._install_thread.join()
