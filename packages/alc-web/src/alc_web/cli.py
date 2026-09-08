"""Launch or reopen one local application instance for a project."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

from ac_jobs import FileLease
from ac_jobs.storage import atomic_write_json

from .store import Store


def _instance(store: Store):
    import httpx

    path = store.root / "server.json"
    try:
        info = json.loads(path.read_text())
        port = info["port"]
        if type(port) is not int or not 1 <= port <= 65535:
            return None
        origin = f"http://127.0.0.1:{port}"
        with httpx.Client(timeout=1, trust_env=False) as client:
            health = client.get(origin + "/health").json()
        if (
            health.get("application") == "alc-web"
            and health.get("instance")
            == hashlib.sha256(info["token"].encode()).hexdigest()
        ):
            return {**info, "origin": origin}
    except (OSError, ValueError, KeyError, httpx.HTTPError):
        pass
    return None


def serve(store: Store, port: int):
    import uvicorn
    from .app import create_app

    lock = FileLease(store.root / "server.lock").acquire(blocking=False)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
        selected = sock.getsockname()[1]
        token = secrets.token_urlsafe(32)
        info = {
            "schema_version": "alc.web.instance.v1",
            "pid": os.getpid(),
            "port": selected,
            "token": token,
        }
        origin = f"http://127.0.0.1:{selected}"
        app = create_app(store.project, token=token, origin=origin)
        atomic_write_json(store.root / "server.json", info)
        os.chmod(store.root / "server.json", 0o600)
        print(f"ALC Web: {origin}/#token={token}", flush=True)
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=selected,
                log_level="warning",
                access_log=False,
                workers=1,
                timeout_graceful_shutdown=3,
            )
        )
        server.run(sockets=[sock])
    finally:
        sock.close()
        lock.release()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="alc-web", description="Start or reopen the local ALC document workspace."
    )
    parser.add_argument("--project-dir", type=Path, default=Path.home() / "ALC")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="keep the server attached to this terminal",
    )
    parser.add_argument(
        "--input", help="prefill the new-job form with a local source or HTTPS URL/DOI"
    )
    parser.add_argument("--target-language", default="zh-CN")
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    store = Store(args.project_dir)
    if args.serve or args.foreground:
        serve(store, args.port)
        return 0
    info = _instance(store)
    if info and args.port and args.port != info["port"]:
        parser.error("This project already has a server on a different port.")
    if not info:
        with (store.root / "server.log").open("ab") as output:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "alc_web",
                    "--serve",
                    "--project-dir",
                    str(store.project),
                    "--port",
                    str(args.port),
                ],
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        for _ in range(120):
            info = _instance(store)
            if info:
                break
            if process.poll() is not None:
                break
            time.sleep(0.25)
        if not info:
            print(
                f"ALC Web could not start. Inspect {store.root / 'server.log'}",
                file=sys.stderr,
            )
            return 1
    query = {"language": args.target_language}
    if args.input:
        path = Path(args.input).expanduser()
        if path.is_file():
            import httpx

            with path.open("rb") as source, httpx.Client(
                timeout=60, trust_env=False
            ) as client:
                response = client.post(
                    info["origin"] + "/api/sources",
                    headers={
                        "Authorization": "Bearer " + info["token"],
                        "Origin": info["origin"],
                    },
                    files={"file": (path.name, source)},
                )
                response.raise_for_status()
                query["source"] = response.json()["id"]
                query["name"] = path.name
        else:
            query["url"] = args.input
    url = info["origin"] + "/?" + urlencode(query) + "#token=" + info["token"]
    print(url)
    if not args.no_open:
        webbrowser.open(url)
    return 0
