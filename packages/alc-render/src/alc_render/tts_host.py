"""Capability-scoped loopback audio access for a single local Reader."""
from __future__ import annotations

import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
import re
import secrets
import select
import socket
import threading


def refresh_reader_runtime(content: bytes) -> bytes:
    """Refresh recognized Reader assets without changing document payloads."""
    html = content.decode('utf-8')
    pattern = re.compile(r'(<script\b[^>]*>)([\s\S]*?)(</script>)', re.I)
    matches = [m for m in pattern.finditer(html) if 'function renderSourceRow(' in m[2]
               and 'function setupEditor(' in m[2]]
    if len(matches) != 1:
        return content
    runtime = files('alc_render').joinpath('web_assets/reader.js').read_text(encoding='utf-8')
    match = matches[0]
    html = html[:match.start(2)] + runtime + html[match.end(2):]
    for name in ('glossary-editor', 'tts-reader'):
        css = files('alc_render').joinpath('web_assets/' + name + '.css').read_text(encoding='utf-8')
        style_id = 'alc-' + name + '-runtime'
        html = re.sub(r'<style id="' + style_id + r'">[\s\S]*?</style>', '', html)
        style = '<style id="' + style_id + '">' + css + '</style>'
        position = html.lower().find('</head>')
        html = html[:position] + style + html[position:] if position >= 0 else style + html
    return html.encode('utf-8')


def _reader_audio_html(content: bytes, endpoint: str, policy: str) -> bytes:
    html = content.decode('utf-8')
    # Only renderer-owned, self-contained documents receive the audio capability.
    if 'id="alc-render-payload"' not in html or 'function renderSourceRow(' not in html:
        return content
    html = re.sub(r'<script\b[^>]*\bid=["\']alc-tts-config["\'][^>]*>[\s\S]*?</script>', '', html, flags=re.I)
    html = re.sub(r'<meta\b(?=[^>]*http-equiv\s*=\s*["\']Content-Security-Policy["\'])[^>]*>', '', html, flags=re.I)
    config = '<script type="application/json" id="alc-tts-config">' + json.dumps({'endpoint': endpoint}) + '</script>'
    meta_policy = re.sub(r'(?:sandbox|frame-ancestors)[^;]*;\s*', '', policy)
    meta = '<meta http-equiv="Content-Security-Policy" content="' + meta_policy.replace('"', '&quot;') + '">'
    position = html.lower().find('</head>')
    if position < 0:
        raise ValueError('Reader HTML has no head element')
    return (html[:position] + meta + config + html[position:]).encode('utf-8')


class ReaderHosts:
    """Serve immutable Readers; audio access never grants task or file APIs."""

    def __init__(self, state_path: Path | None = None, tts_manager=None):
        self._state_path = state_path
        self._tts = tts_manager
        try:
            value = json.loads(state_path.read_text()) if state_path else {}
            self._ports = {k: v for k, v in value.items() if isinstance(k, str) and type(v) is int and 1024 <= v <= 65535}
        except (OSError, ValueError, AttributeError):
            self._ports = {}
        self._hosts = {}
        self._lock = threading.Lock()
        self._audio_slots = threading.BoundedSemaphore(2)

    def open(self, path: Path, digest: str) -> str:
        path = path.resolve()
        key = (str(path), digest)
        with self._lock:
            if key in self._hosts:
                return self._hosts[key][1]
            capability = '/' + secrets.token_urlsafe(32)
            manager, slots = self._tts, self._audio_slots

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *_args):
                    pass

                def origin(self):
                    return f'http://127.0.0.1:{self.server.server_port}'

                def boundary(self, write=False):
                    if self.headers.get('Host') != self.origin().removeprefix('http://'):
                        self.send_error(403); return False
                    origin = self.headers.get('Origin')
                    if (write and origin != self.origin()) or origin not in (None, self.origin()) or self.headers.get('Sec-Fetch-Site') == 'cross-site':
                        self.send_error(403); return False
                    return True

                def respond(self, status, content, media, policy=None):
                    self.send_response(status)
                    self.send_header('Content-Type', media)
                    self.send_header('Content-Length', str(len(content)))
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Referrer-Policy', 'no-referrer')
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    if policy:
                        self.send_header('Content-Security-Policy', policy)
                    self.end_headers()
                    try:
                        self.wfile.write(content)
                    except (BrokenPipeError, ConnectionResetError):
                        pass

                def error(self, status, detail):
                    self.respond(status, json.dumps({'detail': detail}).encode(), 'application/json')

                def do_GET(self):
                    if not self.boundary(): return
                    if manager is not None and self.path == capability + '/tts/status':
                        self.respond(200, json.dumps(manager.status()).encode(), 'application/json'); return
                    if self.path != capability:
                        self.send_error(404); return
                    try:
                        content = path.read_bytes()
                    except OSError:
                        self.send_error(404); return
                    if hashlib.sha256(content).hexdigest() != digest:
                        self.send_error(409); return
                    content = refresh_reader_runtime(content)
                    audio = manager is not None and b'id="alc-render-payload"' in content and b'function renderSourceRow(' in content
                    connect = self.origin() + capability + '/tts/' if audio else "'none'"
                    policy = (
                        "sandbox allow-scripts allow-same-origin allow-downloads allow-modals; "
                        "default-src 'none'; script-src 'unsafe-inline' blob:; "
                        "style-src 'unsafe-inline'; img-src data: blob:; font-src data:; media-src data: blob:; "
                        f"connect-src {connect}; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
                    )
                    if audio:
                        content = _reader_audio_html(content, capability + '/tts', policy)
                    self.respond(200, content, 'text/html; charset=utf-8', policy)

                def do_POST(self):
                    if not self.boundary(write=True): return
                    if manager is None or self.path != capability + '/tts/speech':
                        self.send_error(404); return
                    if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json' or self.headers.get('Transfer-Encoding'):
                        self.error(415, 'Expected a bounded JSON request.'); return
                    try:
                        size = int(self.headers.get('Content-Length', '0'))
                        if not 0 < size <= 65536: raise ValueError()
                    except ValueError:
                        self.error(413, 'Speech request is too large.'); return
                    if not slots.acquire(blocking=False):
                        self.error(429, 'Local speech is busy. Please retry.'); return
                    cancelled, finished = threading.Event(), threading.Event()
                    watcher = None
                    try:
                        self.connection.settimeout(10)
                        value = json.loads(self.rfile.read(size))
                        if not isinstance(value, dict) or set(value) - {'text', 'language', 'voice', 'rate', 'model_id'}:
                            raise ValueError('Invalid speech request.')
                        text = value.get('text')
                        if not isinstance(text, str) or not text.strip() or len(text) > 8000:
                            raise ValueError('Speech text must contain 1–8000 characters.')
                        language = value.get('language', 'zh-CN')
                        voice, rate = value.get('voice'), value.get('rate', 1.0)
                        model_id = value.get('model_id')
                        if model_id is not None and (not isinstance(model_id, str) or not 1 <= len(model_id) <= 100):
                            raise ValueError('Invalid speech model.')
                        if not isinstance(language, str) or (voice is not None and not isinstance(voice, str)) or type(rate) not in (int, float) or not 0.25 <= rate <= 4:
                            raise ValueError('Invalid voice or speech rate.')
                        def watch_disconnect():
                            while not finished.wait(0.1):
                                try:
                                    readable, _, _ = select.select([self.connection], [], [], 0)
                                    if readable and not self.connection.recv(1, socket.MSG_PEEK):
                                        cancelled.set()
                                        return
                                except OSError:
                                    cancelled.set()
                                    return
                        watcher = threading.Thread(target=watch_disconnect, daemon=True)
                        watcher.start()
                        model_options = {'model_id': model_id} if model_id is not None else {}
                        audio = manager.synthesize(text, language=language, voice=voice, rate=rate,
                                                   cancel_event=cancelled, **model_options)
                        finished.set()
                        if not cancelled.is_set():
                            self.respond(200, audio, 'audio/wav')
                    except (ValueError, UnicodeError) as exc:
                        self.error(400, str(exc))
                    except (RuntimeError, OSError):
                        if not cancelled.is_set():
                            self.error(503, '本地朗读不可用，请在设置中检查安装和启用状态。')
                    finally:
                        finished.set()
                        if watcher is not None:
                            watcher.join(timeout=0.2)
                        slots.release()

            port_key = hashlib.sha256((str(path) + digest).encode()).hexdigest()
            try:
                server = ThreadingHTTPServer(('127.0.0.1', self._ports.get(port_key, 0)), Handler)
            except OSError:
                server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            server.daemon_threads = True
            self._ports[port_key] = server.server_port
            if self._state_path:
                self._state_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self._state_path.with_name(self._state_path.name + '.tmp')
                temporary.write_text(json.dumps(self._ports))
                os.replace(temporary, self._state_path)
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
