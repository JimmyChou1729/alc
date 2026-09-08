#!/usr/bin/env python3
"""Bootstrap Local Web from this checkout and a locked Foundation revision."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SCRIPTS = ROOT / "plugins/alc/skills/alc/scripts"


def load_runtime():
    spec = importlib.util.spec_from_file_location(
        "alc_web_private_bootstrap", RUNTIME_SCRIPTS / "ac_runtime.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def frontend_digest(root: Path) -> str:
    app = root / "apps/web"
    paths = [p for p in (app / "src").rglob("*") if p.is_file()]
    paths += [app / name for name in (
        "package.json", "package-lock.json", "index.html", "tsconfig.json", "vite.config.ts"
    )]
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(app)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def ensure_frontend(root: Path, runtime) -> str:
    static = root / "packages/alc-web/src/alc_web/static"
    stamp = static / ".source-fingerprint"
    wanted = frontend_digest(root)
    # A stable lock outside Vite's output directory survives emptyOutDir.
    lock_dir = root / "local/alc-web-bootstrap"
    lock_dir.mkdir(parents=True, exist_ok=True)
    with runtime.InstallLock(lock_dir / "frontend.lock"):
        if (static / "index.html").is_file() and stamp.is_file() and stamp.read_text() == wanted:
            return wanted
        npm = shutil.which("npm")
        if npm is None:
            raise RuntimeError(
                "The source frontend needs building. Install Node.js 20.19 (20.x) or 22.12+ "
                "with npm, then run this command again."
            )
        print("Building the Local Web frontend…", file=sys.stderr)
        for action in ("ci", "run"):
            command = [npm, "--prefix", str(root / "apps/web"), action]
            if action == "run":
                command.append("build")
            subprocess.run(command, cwd=root, check=True, stdout=sys.stderr)
        if not (static / "index.html").is_file():
            raise RuntimeError("Frontend build did not produce index.html.")
        stamp.write_text(wanted)
    return wanted


def prepare_configuration(root: Path, runtime) -> tuple[Path, Path]:
    source_file = root / "plugins/alc/skills/alc/scripts/runtime-sources.json"
    runtime.load_lock(source_file)  # Validate the authoritative lock before deriving it.
    document = json.loads(source_file.read_text())
    document["profile"] = "alc-web"
    for key in ("PYTHONPATH", "PYTHONHOME"):
        document["environment_defaults"].pop(key, None)
    product = next(source for source in document["sources"] if source["id"] == "product")
    if "alc-web" not in product["packages"]:
        product["packages"].append("alc-web")
    if "alc-web" not in product["tools"]:
        product["tools"].append("alc-web")
    # The Web source is always this checkout. Foundation is local only on explicit opt-in.
    os.environ[product["local_root_env"]] = str(root)
    os.environ["AC_INSTALL_SOURCE"] = "mixed"
    cache = Path(os.environ.get("AC_HOME") or "~/.ac").expanduser().resolve()
    content = json.dumps(document, sort_keys=True, indent=2) + "\n"
    constraints = "\n".join((root / path).read_text() for path in (
        "plugins/alc/skills/alc/scripts/runtime-constraints.txt",
        "packages/alc-web/runtime-constraints.txt",
    ))
    constraints += "\n# Frontend source: " + frontend_digest(root) + "\n"
    identity = hashlib.sha256((str(root) + content + constraints).encode()).hexdigest()
    directory = cache / "bootstrap/alc-web" / identity
    directory.mkdir(parents=True, exist_ok=True)
    with runtime.InstallLock(directory / "config.lock"):
        lock_path = directory / "runtime-sources.json"
        constraints_path = directory / "runtime-constraints.txt"
        runtime._atomic_json(lock_path, document)
        temporary = constraints_path.with_suffix(".tmp")
        temporary.write_text(constraints)
        temporary.chmod(0o600)
        temporary.replace(constraints_path)
    return lock_path, constraints_path


def run_installed(arguments: list[str], *, check_only: bool = False) -> int:
    try:
        from ac_llm import ExecutionLimits, LLMExecutionProfile
        from alc_web.app import create_app  # Validate all Web imports before spawning a server.
        from alc_web.cli import main as web_main
        if not hasattr(LLMExecutionProfile, "LOCAL_APP") or not hasattr(ExecutionLimits(), "total_timeout_seconds"):
            raise ImportError("Foundation lacks the required local application execution policy")
    except (ImportError, AttributeError) as exc:
        print(
            "The installed runtime is incompatible with this Local Web checkout. "
            "The release must pin a Foundation commit containing the matching changes. "
            "For development, explicitly set AC_FOUNDATION_REPO_ROOT to a matching checkout. "
            f"Details: {exc}", file=sys.stderr,
        )
        return 78
    if check_only:
        print("Local Web runtime ready.")
        return 0
    return web_main(arguments)


def runtime_doctor(runtime) -> int:
    output = io.StringIO()
    with redirect_stdout(output):
        status = runtime.main(["doctor"])
    document = json.loads(output.getvalue())
    document["installed"] = document["ready"]
    document["compatible"] = False
    if document["installed"]:
        directory = Path(document["runtime"])
        check = subprocess.run(
            [str(runtime._venv_python(directory)), str(Path(__file__).resolve()),
             "--inside-runtime", "--check-only"],
            env=runtime._private_runtime_environment(directory),
            capture_output=True, text=True,
        )
        document["compatible"] = check.returncode == 0
        if check.returncode:
            document["compatibility_error"] = check.stderr.strip()
    document["ready"] = document["installed"] and document["compatible"]
    print(json.dumps(document, ensure_ascii=False, indent=2))
    return 0 if document["ready"] else (status or 1)


def main(arguments: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if arguments is None else arguments)
    if sys.version_info < (3, 11):
        print("Local Web bootstrap requires Python 3.11 or newer.", file=sys.stderr)
        return 69
    if args[:1] == ["--inside-runtime"]:
        return run_installed(args[1:], check_only=args[1:] == ["--check-only"])
    if args in (["--help"], ["-h"]):
        print("Usage: python3 scripts/alc-web.py [--project-dir PATH] [--port PORT] "
              "[--no-open] [--foreground] [--input SOURCE] [--target-language LANGUAGE]\n"
              "       --runtime-setup   Build frontend and install/check the private runtime\n"
              "       --runtime-doctor  Inspect runtime readiness without building or installing\n"
              "First source launch needs Python 3.11+, Git, and Node.js/npm. "
              "uv is used when available; otherwise pip installs into a private venv.")
        return 0
    override = os.environ.get("ALC_WEB_PYTHON")
    if override:
        if any(arg in ("--runtime-doctor", "--runtime-setup") for arg in args):
            print("Unset ALC_WEB_PYTHON to manage the automatic private runtime.", file=sys.stderr)
            return 64
        return subprocess.call([override, "-m", "alc_web", *args])
    # An activated development shell must not override the locked private packages.
    for key in ("PYTHONPATH", "PYTHONHOME"):
        os.environ.pop(key, None)
    try:
        runtime = load_runtime()
        doctor = args == ["--runtime-doctor"]
        setup = args == ["--runtime-setup"]
        if any(arg in ("--runtime-doctor", "--runtime-setup") for arg in args) and not (doctor or setup):
            raise RuntimeError("Use runtime setup/doctor on its own, without Web launch arguments.")
        if not doctor:
            ensure_frontend(ROOT, runtime)
        lock_path, constraints_path = prepare_configuration(ROOT, runtime)
        os.environ["AC_RUNTIME_SOURCES_FILE"] = str(lock_path)
        os.environ["AC_RUNTIME_CONSTRAINTS_FILE"] = str(constraints_path)
        os.environ["AC_RUNTIME_LAUNCHER_NAME"] = "alc-web"
        if doctor:
            return runtime_doctor(runtime)
        command = ["script", str(Path(__file__).resolve()), "--inside-runtime"]
        command += ["--check-only"] if setup else args
        return runtime.main(command)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Local Web setup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
