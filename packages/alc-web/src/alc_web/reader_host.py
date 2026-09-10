"""Serve verified Readers on isolated loopback origins, without Web API access."""
from __future__ import annotations

import hashlib
import json
from ac_jobs import atomic_write_bytes
from importlib.resources import files
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import threading


def refresh_reader_runtime(content: bytes) -> bytes:
    """Update known standalone Reader code without rewriting saved delivery bytes."""
    html = content.decode("utf-8")
    pattern = re.compile(r"(<script\b[^>]*>)([\s\S]*?)(</script>)", re.I)
    matches = [m for m in pattern.finditer(html) if "function renderSourceRow(" in m[2]
               and "function setupEditor(" in m[2]]
    if len(matches) != 1:
        return content
    runtime = files("alc_render").joinpath("web_assets/reader.js").read_text(encoding="utf-8")
    match = matches[0]
    return (html[:match.start(2)] + runtime + html[match.end(2):]).encode("utf-8")


class ReaderHosts:
    def __init__(self, state_path: Path | None = None):
        self._state_path = state_path
        try:
            value = json.loads(state_path.read_text()) if state_path else {}
            self._ports = {k:v for k,v in value.items() if isinstance(k,str) and type(v) is int and 1024 <= v <= 65535}
        except (OSError, ValueError, AttributeError):
            self._ports = {}
        self._hosts = {}
        self._lock = threading.Lock()

    def open(self, path: Path, digest: str) -> str:
        key = (str(path), digest)
        with self._lock:
            if key in self._hosts:
                return self._hosts[key][1]
            capability = '/' + secrets.token_urlsafe(32)

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *_args):
                    pass

                def do_GET(self):
                    if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
                        self.send_error(403)
                        return
                    if self.path != capability:
                        self.send_error(404)
                        return
                    try:
                        content = path.read_bytes()
                    except OSError:
                        self.send_error(404)
                        return
                    if hashlib.sha256(content).hexdigest() != digest:
                        self.send_error(409)
                        return
                    content = refresh_reader_runtime(content)
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(content)))
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Referrer-Policy', 'no-referrer')
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    self.send_header('Content-Security-Policy',
                        "sandbox allow-scripts allow-same-origin allow-downloads allow-modals; "
                        "default-src 'none'; script-src 'unsafe-inline' blob:; "
                        "style-src 'unsafe-inline'; img-src data: blob:; font-src data:; "
                        "connect-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
                    self.end_headers()
                    self.wfile.write(content)

            port_key = hashlib.sha256((str(path) + digest).encode()).hexdigest()
            try:
                server = ThreadingHTTPServer(('127.0.0.1', self._ports.get(port_key, 0)), Handler)
            except OSError:
                server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            self._ports[port_key] = server.server_port
            if self._state_path:
                atomic_write_bytes(self._state_path, json.dumps(self._ports).encode())
            server.daemon_threads = True
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f'http://127.0.0.1:{server.server_port}{capability}'
            self._hosts[key] = (server, url)
            return url

    def close(self):
        with self._lock:
            for server, _url in self._hosts.values():
                server.shutdown()
                server.server_close()
            self._hosts.clear()
