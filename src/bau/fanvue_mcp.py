"""Fanvue's official connection for AI tools (its MCP server): sign in and press Allow, no
developer app, no keys, no redirect address to type (the owner's choice, 2026-11-10, after the
developer app's redirect address kept being refused).

Facts read 2026-11-10 from api.fanvue.com/docs/mcp-server (+ /claude.md, /custom-tools.md)
and the servers' own metadata:
  Server  https://mcp.fanvue.com/mcp, MCP over remote HTTP; unauthenticated calls get 401 with
          WWW-Authenticate: Bearer. 200 requests / 60 s per user per app.
  Auth    https://mcp.fanvue.com/.well-known/oauth-protected-resource names the authorization
          server https://auth.mcp.fanvue.com. Its metadata: dynamic client registration at
          /reg, public clients (token_endpoint_auth_methods_supported: none), PKCE S256,
          authorization code + refresh token, scopes openid offline_access fanvue_mcp:read
          fanvue_mcp:write ("write implies read"). Registering BAU with a loopback redirect
          http://127.0.0.1:3457/callback was accepted (tested 2026-11-10).
  Tools   generated from Fanvue's unversioned API, one per operation; custom__start-image-upload
          and custom__create-image-post (audience subscribers | followers-and-subscribers,
          price in USD cents >= 300). "A post goes live as soon as the tool runs": BAU calls
          posting tools only from the paths that already ran every content check.

Tokens live in BAU_HOME/secrets/fanvue_mcp.json (0600), never logged.
"""

from __future__ import annotations

import http.server
import json
import os
import secrets
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import __version__
from .fanvue import FanvueError, pkce_pair
from .home import atomic_write_json, bau_home

MCP_URL = "https://mcp.fanvue.com/mcp"
AUTH = "https://auth.mcp.fanvue.com"
SCOPES = "openid offline_access fanvue_mcp:write"
PORT = 3457
PROTOCOL_VERSION = "2025-06-18"

# post(url, body bytes, headers) -> (status, headers dict lower-cased, body bytes)
Post = Callable[[str, bytes, dict[str, str]], tuple[int, dict[str, str], bytes]]


def _post(url: str, body: bytes, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()


class Store:
    def __init__(self, home: Path | None = None):
        self.path = (home or bau_home()) / "secrets" / "fanvue_mcp.json"

    def load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, stat.S_IRWXU)
        atomic_write_json(self.path, data)
        os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)

    def connected(self) -> bool:
        return bool(self.load().get("refresh_token") or self.load().get("access_token"))


def _form(post: Post, url: str, fields: dict[str, str]) -> dict[str, Any]:
    status, _, body = post(url, urllib.parse.urlencode(fields).encode(),
                           {"Content-Type": "application/x-www-form-urlencoded",
                            "Accept": "application/json"})
    data = json.loads(body or b"{}")
    if status != 200 or "access_token" not in data:
        raise FanvueError(f"Fanvue refused the sign-in: "
                          f"{data.get('error_description') or data.get('error') or status}")
    return data


def _keep(store: Store, st: dict[str, Any], tok: dict[str, Any]) -> dict[str, Any]:
    st.update(access_token=tok["access_token"],
              # refresh tokens rotate: always keep the newest one
              refresh_token=tok.get("refresh_token") or st.get("refresh_token", ""),
              expires_at=time.time() + int(tok.get("expires_in") or 0) - 60)
    store.save(st)
    return st


def register(store: Store, post: Post = _post, port: int = PORT) -> dict[str, Any]:
    """BAU registers itself with Fanvue's sign-in server once (dynamic registration)."""
    st = store.load()
    redirect = f"http://127.0.0.1:{port}/callback"
    if st.get("client_id") and st.get("redirect") == redirect:
        return st
    status, _, body = post(f"{AUTH}/reg", json.dumps({
        "client_name": "BAU Jarvis", "redirect_uris": [redirect],
        "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": "openid offline_access fanvue_mcp:read fanvue_mcp:write"}).encode(),
        {"Content-Type": "application/json", "Accept": "application/json"})
    data = json.loads(body or b"{}")
    if status not in (200, 201) or not data.get("client_id"):
        raise FanvueError(f"Fanvue did not register BAU: "
                          f"{data.get('error_description') or data.get('error') or status}")
    st = {"client_id": data["client_id"], "redirect": redirect}
    store.save(st)
    return st


def connect(home: Path | None = None, open_browser: Callable[[str], Any] | None = None,
            post: Post = _post, port: int = PORT, timeout: int = 600,
            wait: Callable[[str, str, int, int], dict[str, str]] | None = None
            ) -> dict[str, Any]:
    """The owner signs in on Fanvue and presses Allow; BAU keeps the tokens."""
    store = Store(home)
    st = register(store, post, port)
    verifier, challenge = pkce_pair()
    state = secrets.token_hex(32)
    url = f"{AUTH}/oauth2/auth?" + urllib.parse.urlencode({
        "client_id": st["client_id"], "redirect_uri": st["redirect"], "response_type": "code",
        "scope": SCOPES, "state": state, "code_challenge": challenge,
        "code_challenge_method": "S256", "resource": MCP_URL})
    (open_browser or (lambda u: print(f"Open this link to connect Fanvue:\n{u}")))(url)
    got = (wait or _wait)(url, state, port, timeout)
    if not secrets.compare_digest(got.get("state", ""), state):
        raise FanvueError("state mismatch - sign-in stopped")
    if "code" not in got:
        raise FanvueError(f"Fanvue refused: {got.get('error_description') or got.get('error')}")
    tok = _form(post, f"{AUTH}/oauth2/token", {
        "grant_type": "authorization_code", "code": got["code"], "client_id": st["client_id"],
        "redirect_uri": st["redirect"], "code_verifier": verifier, "resource": MCP_URL})
    return _keep(store, st, tok)


def _wait(url: str, state: str, port: int, timeout: int) -> dict[str, str]:
    """Answer requests on 127.0.0.1 until Fanvue's reply comes (a favicon request first, or
    a reload, no longer ends the sign-in), or `timeout` seconds pass."""
    got: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
            if "code" in q or "error" in q:
                got.update(q)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"BAU: Fanvue connected. You can close this tab." if got
                             else b"BAU is waiting for Fanvue.")

        def log_message(self, *a: Any) -> None:
            pass

    srv = http.server.HTTPServer(("127.0.0.1", port), Handler)
    srv.timeout = 5
    end = time.time() + timeout
    try:
        while not got and time.time() < end:
            srv.handle_request()
    finally:
        srv.server_close()
    if not got:
        raise FanvueError("no answer from Fanvue in time: run it again and press Allow")
    return got


def access_token(home: Path | None = None, post: Post = _post) -> str:
    store = Store(home)
    st = store.load()
    if not st.get("access_token"):
        raise FanvueError("Fanvue is not connected: bau fanvue connect")
    if time.time() < float(st.get("expires_at", 0)):
        return str(st["access_token"])
    if not st.get("refresh_token"):
        raise FanvueError("the Fanvue sign-in ran out: bau fanvue connect")
    tok = _form(post, f"{AUTH}/oauth2/token", {
        "grant_type": "refresh_token", "refresh_token": st["refresh_token"],
        "client_id": st["client_id"], "resource": MCP_URL})
    return str(_keep(store, st, tok)["access_token"])


def _messages(headers: dict[str, str], body: bytes) -> list[dict[str, Any]]:
    """A JSON body, or a server-sent event stream of JSON messages."""
    if "text/event-stream" in headers.get("content-type", ""):
        out = []
        for line in body.decode("utf-8", "replace").splitlines():
            if line.startswith("data:") and line[5:].strip():
                out.append(json.loads(line[5:]))
        return out
    data = json.loads(body or b"{}")
    return data if isinstance(data, list) else [data]


class FanvueMcp:
    """Fanvue's MCP server over HTTP: initialize, list tools, call one."""

    def __init__(self, home: Path | None = None, post: Post = _post):
        self.home, self.post, self.session, self._id = home, post, "", 0

    def _send(self, msg: dict[str, Any]) -> list[dict[str, Any]]:
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": PROTOCOL_VERSION,
                   "Authorization": f"Bearer {access_token(self.home, self.post)}"}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        status, h, body = self.post(MCP_URL, json.dumps(msg).encode(), headers)
        if status == 401:
            raise FanvueError("Fanvue asked to sign in again: bau fanvue connect")
        if status >= 400:
            raise FanvueError(f"Fanvue's server answered {status}: {body[:200]!r}")
        self.session = h.get("mcp-session-id", self.session)
        return _messages(h, body) if body else []

    def _request(self, method: str, params: dict[str, Any]) -> Any:
        self._id += 1
        for m in self._send({"jsonrpc": "2.0", "id": self._id, "method": method,
                             "params": params}):
            if m.get("id") == self._id:
                if "error" in m:
                    raise FanvueError(f"{method}: {m['error'].get('message')}")
                return m.get("result") or {}
        raise FanvueError(f"no answer to {method}")

    def initialize(self) -> dict[str, Any]:
        res = self._request("initialize", {"protocolVersion": PROTOCOL_VERSION,
                                           "capabilities": {},
                                           "clientInfo": {"name": "bau", "version": __version__}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return res

    def list_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        cursor = None
        while True:
            res = self._request("tools/list", {"cursor": cursor} if cursor else {})
            tools += res.get("tools", [])
            cursor = res.get("nextCursor")
            if not cursor:
                return tools

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        res = self._request("tools/call", {"name": name, "arguments": arguments})
        text = "\n".join(c.get("text", "") for c in res.get("content", [])
                         if c.get("type") == "text")
        return {"text": text, "data": res.get("structuredContent"),
                "is_error": bool(res.get("isError"))}
