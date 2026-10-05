"""Jarvis HUD server (stdlib only).

Unlike Mission Control this server can act, so it runs as the owner (started by
``bau jarvis`` from their own login) and is locked down accordingly:

* bound to 127.0.0.1, and the Host header must be a local name (DNS rebinding);
* the page is only served with the per-launch key from the URL ``bau jarvis``
  opens, and every API call must carry that key in a custom header - which other
  web sites cannot send without a CORS preflight this server never grants;
* a present Origin header must be this server's own;
* bodies are size-limited, and the model can only *stage* consequential actions:
  they run when the owner presses Confirm (``/api/confirm``).
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import shutil
import threading
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any

from ..assistant import Assistant, Voice
from .server import allowed_hosts_from_env, bind_address

MAX_JSON = 64 * 1024
MAX_AUDIO = 8 * 1024 * 1024


def make_handler(assistant: Assistant, voice: Voice, key: str
                 ) -> type[BaseHTTPRequestHandler]:
    page = (resources.files("bau.ui") / "jarvis.html").read_bytes()
    allowed_hosts = allowed_hosts_from_env()
    lock = threading.Lock()               # one conversation, one turn at a time

    class H(BaseHTTPRequestHandler):
        server_version = "BAU-Jarvis"

        def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Permissions-Policy", "microphone=(self)")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; script-src 'unsafe-inline'; "
                             "style-src 'unsafe-inline'; connect-src 'self'; "
                             "media-src 'self' blob:; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: Any) -> None:
            self._send(code, json.dumps(obj, default=str).encode())

        def _guard(self, api: bool) -> bool:
            host = (self.headers.get("Host") or "").split(":")[0].lower()
            if host not in allowed_hosts:
                self._send(421, b"local access only", "text/plain")
                return False
            origin = self.headers.get("Origin")
            if origin is not None:
                o_host = origin.split("://", 1)[-1].split(":")[0].lower()
                if o_host not in allowed_hosts or o_host != host:
                    self._send(403, b"cross-origin request refused", "text/plain")
                    return False
            if api and not hmac.compare_digest(self.headers.get("X-Jarvis-Key", ""), key):
                self._send(403, b"missing or wrong Jarvis key", "text/plain")
                return False
            return True

        def _body(self, limit: int) -> bytes | None:
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = -1
            if n < 0 or n > limit:
                self._send(413, b"request too large", "text/plain")
                return None
            return self.rfile.read(n)

        def _state(self) -> dict[str, Any]:
            return {"call_me": assistant.cfg["call_me"],
                    "mode": "model" if assistant.provider else "plain",
                    "model": assistant.model.get("id") or assistant.model.get("api_model"),
                    "voice": voice.available, "listen": voice.can_listen,
                    "pending": [p.public() for p in assistant.pending.values()]}

        def do_GET(self) -> None:  # noqa: N802
            path, _, query = self.path.partition("?")
            if path in ("/", "/index.html"):
                if not self._guard(api=False):
                    return
                got = dict(p.partition("=")[::2] for p in query.split("&") if p)
                if not hmac.compare_digest(got.get("k", ""), key):
                    self._send(403, b"Open Jarvis with the link that 'bau jarvis' printed.",
                               "text/plain")
                    return
                self._send(200, page, "text/html; charset=utf-8")
                return
            if not path.startswith("/api/"):
                self._send(404, b"not found", "text/plain")
                return
            if not self._guard(api=True):
                return
            if path.startswith("/api/preview/"):
                # Only the file a staged card points at - never an arbitrary path.
                p = assistant.pending.get(path.rsplit("/", 1)[-1])
                if p is None or not p.preview:
                    self._send(404, b"not found", "text/plain")
                    return
                try:
                    f = open(p.preview, "rb")   # noqa: SIM115 - closed below
                except OSError:
                    self._send(404, b"not found", "text/plain")
                    return
                with f:
                    size = os.fstat(f.fileno()).st_size
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Length", str(size))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    shutil.copyfileobj(f, self.wfile, 1024 * 1024)
            elif path == "/api/state":
                self._json(200, self._state())
            elif path == "/api/briefing":
                with lock:
                    r = assistant.briefing()
                self._json(200, {**asdict(r), "state": self._state()})
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:  # noqa: N802
            if not self._guard(api=True):
                return
            if self.path == "/api/stt":
                audio = self._body(MAX_AUDIO)
                if audio is None:
                    return
                text = voice.listen(audio, self.headers.get("Content-Type") or "audio/webm")
                self._json(200 if text is not None else 503, {"text": text})
                return
            raw = self._body(MAX_JSON)
            if raw is None:
                return
            if "application/json" not in (self.headers.get("Content-Type") or ""):
                self._send(415, b"JSON only", "text/plain")
                return
            try:
                data = json.loads(raw or b"{}")
                if not isinstance(data, dict):
                    raise ValueError
            except ValueError:
                self._send(400, b"bad JSON", "text/plain")
                return
            if self.path == "/api/ask":
                with lock:
                    r = assistant.ask(str(data.get("text", "")))
                self._json(200, {**asdict(r), "state": self._state()})
            elif self.path == "/api/confirm":
                # The click on Confirm is the owner's act; the identity is the human
                # who started this server from their own login.
                with lock:
                    choices = data.get("choices")
                    out = assistant.confirm(str(data.get("id", "")),
                                            data.get("approve") is True, assistant.owner,
                                            choices if isinstance(choices, dict) else None)
                self._json(200, {**out, "state": self._state()})
            elif self.path == "/api/tts":
                audio = voice.speak(str(data.get("text", ""))[:2500])
                if audio is None:
                    self._send(204, b"", "text/plain")
                else:
                    self._send(200, audio, "audio/mpeg")
            else:
                self._send(404, b"not found", "text/plain")

        def do_PUT(self) -> None:  # noqa: N802
            self._send(405, b"not allowed", "text/plain")

        do_DELETE = do_PATCH = do_OPTIONS = do_PUT  # noqa: N815

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    return H


def serve(assistant: Assistant, voice: Voice, port: int = 8766, key: str | None = None
          ) -> tuple[ThreadingHTTPServer, str]:
    if not assistant.owner.startswith("human:"):
        raise PermissionError("Jarvis runs for a human owner; start it from your own login")
    key = key or secrets.token_urlsafe(24)
    srv = ThreadingHTTPServer((bind_address(), port), make_handler(assistant, voice, key))
    return srv, key
