"""Mission Control HTTP server (stdlib only).

Bound to 127.0.0.1 and read-only: no endpoint changes state, so a malicious web
page cannot use the browser to approve, send or pay. JSON endpoints require a
custom header (blocks simple cross-site reads) and refuse non-local Host headers
(DNS-rebinding defence).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any

from ..home import bau_home


def _api(path: str, home: Path) -> Any:
    if path == "/api/status":
        from ..status import dashboard
        return dashboard(home)
    if path == "/api/regulations":
        import datetime as dt

        from ..regulations import Registry
        on = dt.date.today()
        return [{"reg_id": r.reg_id, "jurisdiction": r["jurisdiction"],
                 "legal_status": r["legal_status"], "bau_status": r["bau_status"],
                 "applicability": r.applicability(on), "next_review": str(r["next_review"])}
                for r in Registry.load()]
    if path == "/api/jobs":
        from ..jobs import JobStore
        return [{k: v for k, v in asdict(j).items()
                 if k in ("job_id", "agent", "status", "objective", "cost_usd")}
                for j in JobStore(home).all()]
    if path == "/api/missions":
        from ..jarvis import Jarvis
        from ..policy import PolicyEngine
        from ..regulations import Registry
        j = Jarvis(PolicyEngine.load(Registry.load()), home)
        return [{"mission_id": m.mission_id, "mission_type": m.mission_type,
                 "status": m.status, "next_action": m.next_action} for m in j.list()]
    if path == "/api/legal-queue":
        from ..legal_queue import LegalQueue
        return LegalQueue(home).items()
    if path == "/api/economics":
        from ..economics import Ledger, metrics, usage_dashboard
        led = Ledger(home)
        return {"metrics": metrics(led), "usage": usage_dashboard(led, home)}
    if path == "/api/brain":
        from ..brain import Brain
        b = Brain(home)
        g = b.graph()
        return {"nodes": g["nodes"], "edges": g["edges"], "lint": b.lint()[:200],
                "workflows": b.workflows()}
    if path == "/api/governor":
        from ..audit import AuditLog
        from ..governor import Governor
        g = Governor(home, audit=AuditLog(home / "audit" / "chain.jsonl"))
        d = g.digest(72)
        return {"hold": d["hold"], "needs_you": d["needs_you"], "fixed": d["fixed"][-50:],
                "counts": d["counts"]}
    if path == "/api/incidents":
        from ..incidents import Incidents
        return Incidents(home).open_items()
    raise KeyError(path)


def make_handler(home: Path) -> type[BaseHTTPRequestHandler]:
    page = (resources.files("bau.ui") / "page.html").read_bytes()

    class H(BaseHTTPRequestHandler):
        server_version = "BAU-MissionControl"

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; script-src 'unsafe-inline'; "
                             "style-src 'unsafe-inline'; connect-src 'self'; "
                             "frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            host = (self.headers.get("Host") or "").split(":")[0]
            if host not in ("127.0.0.1", "localhost"):
                self._send(421, b"local access only", "text/plain")
                return
            if self.path in ("/", "/index.html"):
                self._send(200, page, "text/html; charset=utf-8")
                return
            if not self.path.startswith("/api/"):
                self._send(404, b"not found", "text/plain")
                return
            if self.headers.get("X-BAU") != "1":
                self._send(403, b"missing X-BAU header", "text/plain")
                return
            try:
                data = _api(self.path, home)
            except KeyError:
                self._send(404, b"not found", "text/plain")
                return
            self._send(200, json.dumps(data, default=str).encode(), "application/json")

        def do_POST(self) -> None:  # noqa: N802
            self._send(405, b"Mission Control is read-only; use the bau CLI", "text/plain")

        do_PUT = do_DELETE = do_PATCH = do_POST  # noqa: N815

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    return H


def serve(port: int = 8765, home: Path | None = None) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(home or bau_home()))
    return srv
