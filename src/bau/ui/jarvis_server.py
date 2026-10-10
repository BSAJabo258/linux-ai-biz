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
import urllib.parse
from collections.abc import Callable
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any

from ..assistant import Assistant, Voice
from . import screen
from .server import allowed_hosts_from_env, bind_address

MAX_JSON = 64 * 1024
MAX_EDIT_JSON = 256 * 1024     # only for saving a stage draft edited on screen
MAX_AUDIO = 8 * 1024 * 1024
QUICK_REPLY = 15        # seconds a request waits for an answer before it becomes a job
MAX_JOBS = 50


def make_handler(assistant: Assistant, voice: Voice, key: str
                 ) -> type[BaseHTTPRequestHandler]:
    page = (resources.files("bau.ui") / "jarvis.html").read_bytes()
    allowed_hosts = allowed_hosts_from_env()
    lock = threading.Lock()               # one conversation, one turn at a time
    # GitHub wants requests one at a time, so one search or inspection at a time; testing
    # a model has its own lane. Neither holds up the conversation.
    lanes = {"scout": threading.Lock(), "models": threading.Lock(),
             "studio": threading.Lock()}
    jobs: dict[str, dict[str, Any]] = {}  # slow answers the page is checking back on

    def state() -> dict[str, Any]:
        return {"call_me": assistant.cfg["call_me"],
                "mode": "model" if assistant.provider else "plain",
                "model": assistant.model.get("id") or assistant.model.get("api_model"),
                "backups": list(assistant.model.get("fallbacks") or []),
                "answered_by": assistant.last_model,
                "voice": voice.available, "listen": voice.can_listen,
                "pending": [p.public() for p in assistant.pending.values()]}

    def waiting() -> list[dict[str, Any]]:
        """What already waits for the owner while a slow answer is still being written: a
        drafted stage's check must not sit unseen until the model finishes talking."""
        return [p.public() for p in list(assistant.pending.values())]

    def answer(work: Callable[[], dict[str, Any]], lane: threading.Lock | None = None
               ) -> tuple[int, dict[str, Any]]:
        """Run one piece of model work. A quick answer comes back at once; a slow one (a
        busy free hosted model can take minutes) becomes a job the page checks every few
        seconds, so no proxy in between - Codespaces, VS Code port forwarding - cuts a
        long request off (the owner saw 504)."""
        box: dict[str, Any] = {}

        def run() -> None:
            try:
                with lane or lock:
                    box["reply"] = work()
            except Exception as e:  # never leave the page waiting for nothing
                box["reply"] = {"text": f"Something went wrong on my side "
                                        f"({type(e).__name__}). Ask me again?",
                                "cards": [], "pending": [], "mode": "plain",
                                "error": str(e)[:300]}

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(QUICK_REPLY)
        if "reply" in box:
            return 200, box["reply"]
        job = secrets.token_urlsafe(12)
        for old in list(jobs)[:-MAX_JOBS]:        # a page that never came back
            jobs.pop(old, None)
        jobs[job] = box
        return 202, {"job": job, "pending": waiting()}

    class H(BaseHTTPRequestHandler):
        server_version = "BAU-Jarvis"

        def handle(self) -> None:
            try:
                super().handle()
            except (BrokenPipeError, ConnectionResetError):
                # The page stopped waiting (reload, closed tab, or the Codespaces proxy
                # giving up on a slow model): there is no one left to send the reply to.
                pass

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
            return state()

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
            elif path == "/api/overview":
                from ..overview import overview
                with lock:
                    self._json(200, overview(assistant))
            elif path == "/api/activity":
                q = dict(p.partition("=")[::2] for p in query.split("&") if p)
                try:
                    since = int(q.get("since") or 0)
                except ValueError:
                    since = 0
                self._json(200, assistant.activity.since(since))
            elif path == "/api/toolbox":
                q = dict(p.partition("=")[::2] for p in query.split("&") if p)
                self._json(200, assistant.t_toolbox(urllib.parse.unquote_plus(
                    q.get("q", ""))))
            elif path == "/api/usage":
                self._json(200, screen.usage_summary(assistant))
            elif path == "/api/studio":
                self._json(*answer(lambda: screen.studio_summary(assistant), lanes["studio"]))
            elif path.startswith("/api/studio/clip/"):
                f = screen.studio_clip(assistant, path.rsplit("/", 1)[-1])
                if f is None:
                    self._send(404, b"not found", "text/plain")
                    return
                with f.open("rb") as fh:
                    size = os.fstat(fh.fileno()).st_size
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Length", str(size))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    shutil.copyfileobj(fh, self.wfile, 1024 * 1024)
            elif path == "/api/scout":
                self._json(200, screen.scout_summary(assistant))
            elif path == "/api/scout/report":
                q = dict(p.partition("=")[::2] for p in query.split("&") if p)
                self._json(200, screen.scout_report(assistant, q.get("run")))
            elif path == "/api/ws/stage":
                q = {k: urllib.parse.unquote_plus(v) for k, v in
                     (p.partition("=")[::2] for p in query.split("&") if p)}
                self._json(200, screen.stage_read(assistant, q.get("workspace", ""),
                                                  q.get("episode", ""), q.get("stage", "")))
            elif path == "/api/timeline":
                q = dict(p.partition("=")[::2] for p in query.split("&") if p)
                try:
                    limit = int(q.get("limit") or 50)
                    before = int(q["before"]) if q.get("before") else None
                except ValueError:
                    limit, before = 50, None
                self._json(200, screen.timeline(assistant, limit, before))
            elif path.startswith("/api/mc/"):
                try:
                    self._json(200, screen.mission_control(assistant, path[len("/api/mc/"):]))
                except KeyError:
                    self._json(404, {"error": "no such view"})
            elif path == "/api/briefing":
                self._json(*answer(lambda: {**asdict(assistant.briefing()), "state": state()}))
            elif path.startswith("/api/job/"):
                job = path.rsplit("/", 1)[-1]
                box = jobs.get(job)
                if box is None:
                    self._json(404, {"error": "no such job (already answered?)"})
                elif "reply" in box:
                    self._json(200, jobs.pop(job)["reply"])
                else:
                    self._json(202, {"job": job, "pending": waiting()})
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
            raw = self._body(MAX_EDIT_JSON if self.path == "/api/ws/stage" else MAX_JSON)
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
                text = str(data.get("text", ""))
                self._json(*answer(lambda: {**asdict(assistant.ask(text)), "state": state()}))
            elif self.path == "/api/confirm":
                # The click on Confirm is the owner's act; the identity is the human
                # who started this server from their own login.
                choices = data.get("choices")

                def confirm() -> dict[str, Any]:
                    out = assistant.confirm(str(data.get("id", "")),
                                            data.get("approve") is True, assistant.owner,
                                            choices if isinstance(choices, dict) else None)
                    return {**out, "state": state()}
                self._json(*answer(confirm))
            elif self.path == "/api/draft":
                # The owner pressed Draft on an episode: the same act Jarvis may do.
                def draft() -> dict[str, Any]:
                    out, err = assistant._run_tool("draft_stage", {
                        "workspace": str(data.get("workspace", "")),
                        "episode": str(data.get("episode", ""))})
                    p = assistant.pending.get(out.get("pending_id", "")) if not err else None
                    return {"result": out, "error": err,
                            "pending": [p.public()] if p else []}
                self._json(*answer(draft))
            elif self.path == "/api/check":
                # Checking is the owner's: this only puts it on screen; Confirm does it.
                from ..workspace import WorkspaceError
                try:
                    with lock:
                        p = assistant.stage_check(str(data.get("workspace", "")),
                                                  str(data.get("episode", "")),
                                                  str(data.get("stage", "")))
                    self._json(200, {"pending": [p]})
                except WorkspaceError as e:
                    self._json(200, {"error": str(e)[:400]})
            elif self.path == "/api/studio/stage":
                # Prices the clip and puts it on screen; only the owner's Confirm starts it.
                self._json(*answer(lambda: screen.studio_stage(assistant, data),
                                   lanes["studio"]))
            elif self.path == "/api/scout/find":
                req = str(data.get("request", ""))
                self._json(*answer(lambda: screen.scout_find(assistant, req), lanes["scout"]))
            elif self.path == "/api/scout/inspect":
                repo = str(data.get("repo", ""))
                self._json(*answer(lambda: screen.scout_inspect(assistant, repo),
                                   lanes["scout"]))
            elif self.path == "/api/models/bench":
                model = str(data.get("model", ""))
                self._json(*answer(lambda: screen.bench(assistant, model), lanes["models"]))
            elif self.path == "/api/ws/stage":
                with lock:
                    self._json(200, screen.stage_write(
                        assistant, str(data.get("workspace", "")), str(data.get("episode", "")),
                        str(data.get("stage", "")), str(data.get("text", ""))))
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


def service_key(path: Path) -> str:
    """The fixed key for Jarvis running as a service (on the owner's cloud server): made
    once, readable by the owner only, the same after every restart."""
    try:
        key = path.read_text().strip()
        if len(key) >= 32:
            return key
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = secrets.token_urlsafe(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(key + "\n")
    os.chmod(path, 0o600)
    return key


def serve(assistant: Assistant, voice: Voice, port: int = 8766, key: str | None = None
          ) -> tuple[ThreadingHTTPServer, str]:
    if not assistant.owner.startswith("human:"):
        raise PermissionError("Jarvis runs for a human owner; start it from your own login")
    key = key or secrets.token_urlsafe(24)
    srv = ThreadingHTTPServer((bind_address(), port), make_handler(assistant, voice, key))
    return srv, key
