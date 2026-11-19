"""Integration doctor: how each platform connects, why a connection fails, and what worked
last time (docs/INTEGRATIONS.md).

Found 2026-11-18: the Fanvue sign-in failed for days because the redirect address BAU sends
(http://127.0.0.1:3456/callback) was not registered on the owner's Fanvue app. Fanvue then
shows its own error page and never calls back, so BAU only timed out. Nothing told the owner
which of the many moving parts (keys, address, port, browser, token, scopes) was wrong.

This module adds, for every OAuth platform BAU already has (Fanvue, TikTok), without a second
sign-in flow (the sign-in itself stays in fanvue.py / tiktok.py, its tokens in credentials.py):
- REGISTRY: endpoints, callback, port, scopes, docs, date checked; never a credential value;
- preflight(): app keys, callback handler, port free, the exact redirect address, and (Fanvue)
  a probe of Fanvue's authorize page that tells "address not registered" and "unknown app"
  apart BEFORE the browser opens;
- Recorder: the flight recorder, one redacted line per stage of every attempt in
  BAU_HOME/integrations/attempts.jsonl, and a copyable report;
- state(): one of STATES. API_VERIFIED only after a real authenticated API call worked;
- known_good: the address, port and scopes of the last verified connection, reused by
  preflight to say what changed.
Secrets (codes, tokens, client secrets, cookies, passwords, wallet keys) are never written:
redact() runs on everything the recorder stores or prints.
"""

from __future__ import annotations

import datetime as dt
import errno
import json
import os
import re
import secrets
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .home import atomic_write_json, bau_home

STATES = ("NOT_CONFIGURED", "CONFIGURED", "READY_TO_AUTHORIZE", "AUTHORIZATION_PENDING",
          "CALLBACK_RECEIVED", "TOKEN_EXCHANGE_PENDING", "AUTHENTICATED", "API_VERIFIED",
          "REFRESH_REQUIRED", "EXPIRED", "REVOKED", "PERMISSION_DENIED", "CONFIGURATION_ERROR",
          "NETWORK_ERROR", "PROVIDER_ERROR", "NEEDS_OWNER_ACTION")

CHECKED = "2026-11-18"
# What BAU actually has. Endpoints re-read on CHECKED from the pages in "docs"; the planned
# platforms are in docs/INTEGRATIONS.md (no code for them yet, so none here).
REGISTRY: dict[str, dict[str, Any]] = {
    "fanvue": {
        "kind": "oauth", "module": "fanvue", "keys": ("FANVUE_CLIENT_ID", "FANVUE_CLIENT_SECRET"),
        "authorize": "https://auth.fanvue.com/oauth2/auth",
        "token": "https://auth.fanvue.com/oauth2/token", "api": "https://api.fanvue.com",
        "api_version": "2025-06-26", "port": 3456, "path": "/callback", "scope_sep": " ",
        "pkce": "S256 base64url", "client_auth": "client_secret_basic", "revoke": None,
        "refresh": "rotating, single-use", "probe": True,
        "health": "GET /v1/users/me (read:self)",
        "register_at": "your Fanvue app > Authentication tab > Redirect URIs, then Save",
        "docs": ["https://api.fanvue.com/docs/authentication/implementation-guide",
                 "https://api.fanvue.com/docs/authentication/scopes",
                 "https://api.fanvue.com/docs/authentication/overview",
                 "https://legal.fanvue.com/api-policy"]},
    "tiktok": {
        "kind": "oauth", "module": "tiktok", "keys": ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET"),
        "authorize": "https://www.tiktok.com/v2/auth/authorize/",
        "token": "https://open.tiktokapis.com/v2/oauth/token/",
        "api": "https://open.tiktokapis.com", "api_version": "v2", "port": 3455,
        "path": "/callback/", "scope_sep": ",", "pkce": "S256 hex (desktop)",
        "client_auth": "client_key + client_secret in the form body",
        "revoke": "https://open.tiktokapis.com/v2/oauth/revoke/",
        "refresh": "access 2 h, refresh 180 days, rotates", "probe": False,
        "health": "POST /v2/post/publish/creator_info/query/",
        "register_at": "TikTok developer portal > your app > Login Kit > Desktop > Redirect URI",
        "docs": ["https://developers.tiktok.com/doc/login-kit-desktop",
                 "https://developers.tiktok.com/doc/oauth-get-a-user-access-token",
                 "https://developers.tiktok.com/doc/oauth-user-access-token-management",
                 "https://developers.tiktok.com/doc/oauth-revoke-a-user-access-token"]},
}

# ------------------------------------------------------------------ redaction

SECRET_KEYS = re.compile(r"(^|_)(code|access_token|refresh_token|id_token|token|secret|"
                         r"client_secret|password|passwd|cookie|session|authorization|"
                         r"code_verifier|verifier|private_key|wallet_secret|seed|mnemonic|"
                         r"api_key|key_secret)$", re.I)
SECRET_TEXT = [
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 [redacted]"),
    (re.compile(r"(?i)([?&](?:code|access_token|refresh_token|id_token|client_secret|"
                r"code_verifier|token)=)[^&\s\"']+"), r"\1[redacted]"),
    (re.compile(r"(?i)(\"?(?:access_token|refresh_token|client_secret|id_token|password)"
                r"\"?\s*[:=]\s*\"?)[^\s\",&]+"), r"\1[redacted]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
     "[redacted private key]"),
]


def redact(obj: Any) -> Any:
    """A copy with every secret-looking value replaced; safe to log, print or paste."""
    if isinstance(obj, dict):
        return {k: ("[redacted]" if SECRET_KEYS.search(str(k)) and v not in (None, "")
                    else redact(v)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact(v) for v in obj]
    if isinstance(obj, str):
        for rx, sub in SECRET_TEXT:
            obj = rx.sub(sub, obj)
        return obj
    return obj


# ------------------------------------------------------------------ flight recorder

def _dir(home: Path | None, make: bool = False) -> Path:
    """BAU_HOME/integrations; only writers create it (a status read changes nothing)."""
    d = (home or bau_home()) / "integrations"
    if make:
        d.mkdir(parents=True, exist_ok=True)
    return d


class Recorder:
    """One connection attempt. Each stage is one redacted line in attempts.jsonl."""

    def __init__(self, provider: str, home: Path | None = None, via: str = "terminal"):
        self.provider, self.home, self.via = provider, home, via
        self.attempt = "att_" + secrets.token_hex(5)
        self.path = _dir(home, make=True) / "attempts.jsonl"

    def stage(self, stage: str, ok: bool, **fields: Any) -> dict[str, Any]:
        rec = redact({"provider": self.provider, "attempt": self.attempt, "via": self.via,
                      "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                      "stage": stage, "ok": ok, **fields})
        with self.path.open("a") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
        try:
            os.chmod(self.path, 0o660)
        except OSError:
            pass
        return rec


def attempts(provider: str, home: Path | None = None) -> list[dict[str, Any]]:
    path = _dir(home) / "attempts.jsonl"
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("provider") == provider:
            out.append(rec)
    return out


def last_attempt(provider: str, home: Path | None = None) -> list[dict[str, Any]]:
    recs = attempts(provider, home)
    if not recs:
        return []
    last = recs[-1]["attempt"]
    return [r for r in recs if r["attempt"] == last]


# ------------------------------------------------------------------ known good

def known_good(provider: str, home: Path | None = None) -> dict[str, Any] | None:
    try:
        return json.loads((_dir(home) / f"{provider}.known_good.json").read_text())
    except (OSError, ValueError):
        return None


def save_known_good(provider: str, home: Path | None, redirect: str, port: int,
                    granted: str, account: str | None, via: str) -> dict[str, Any]:
    """The procedure that worked, so the next connection (or the next platform) starts there."""
    reg = REGISTRY[provider]
    rec = {"provider": provider, "verified_at": dt.datetime.now(dt.UTC)
           .isoformat(timespec="seconds"), "via": via, "redirect": redirect, "port": port,
           "granted_scopes": granted, "account": account,
           "steps": [f"app keys {', '.join(reg['keys'])} in /etc/bau/platforms.env",
                     f"{redirect} registered at: {reg['register_at']}",
                     f"port {port} free on 127.0.0.1, browser on this computer",
                     f"bau {provider} login (or Jarvis's Connect card), press Allow",
                     f"health check {reg['health']} answered"]}
    atomic_write_json(_dir(home, make=True) / f"{provider}.known_good.json", redact(rec))
    return rec


# ------------------------------------------------------------------ checks

def redirect_for(provider: str, port: int | None = None) -> str:
    reg = REGISTRY[provider]
    return f"http://127.0.0.1:{port or reg['port']}{reg['path']}"


def port_check(port: int, host: str = "127.0.0.1") -> tuple[bool, str]:
    """Can the callback listener bind here right now? (It binds only during a sign-in.)"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, port))
        return True, f"{host}:{port} is free"
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            return False, (f"{host}:{port} is already in use (another sign-in still waiting, "
                           f"or another program): find it with  ss -ltnp 'sport = :{port}'")
        return False, f"cannot listen on {host}:{port}: {e}"
    finally:
        s.close()


def scope_diff(requested: str, granted: str, sep: str = " ") -> list[str]:
    """Requested scopes the platform did not grant (empty when all were granted)."""
    want = [s for s in requested.replace(",", " ").split() if s]
    got = {s for s in granted.replace(",", " ").split() if s}
    return [s for s in want if s not in got] if got else []


class _NoFollow(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a: Any, **k: Any) -> None:
        return None


def _get_no_follow(url: str, timeout: int = 15) -> tuple[int, str]:
    opener = urllib.request.build_opener(_NoFollow)
    try:
        with opener.open(url, timeout=timeout) as r:
            return r.status, r.headers.get("Location", "")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Location", "") if e.headers else ""


def classify_authorize(status: int, location: str, redirect: str) -> tuple[str, str]:
    """What Fanvue's authorize page did with our request (read 2026-11-18, live):
    registered address -> 302 to fanvue.com/oauth/login?login_challenge=...;
    unregistered -> 302 to fanvue.com/oauth/error?error=invalid_request ... redirect_uri;
    unknown app -> the same error page with error=invalid_client."""
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(location).query))
    err, why = q.get("error", ""), q.get("error_description", "")
    if err == "invalid_request" and "redirect_uri" in why:
        return "redirect_not_registered", why[:300]
    if err == "invalid_client":
        return "unknown_client", why[:300]
    if location.startswith(redirect):
        return ("ok" if not err else f"provider_error:{err}"), why[:300]
    if err:
        return f"provider_error:{err}", why[:300]
    if status in (301, 302, 303, 307, 308) and location:
        return "ok", ""
    return f"unexpected:{status}", location[:200]


def probe_authorize(provider: str, client_id: str, redirect: str, scopes: str,
                    get: Any = None) -> tuple[str, str]:
    """Ask the platform's authorize page whether it accepts this app + address, without a
    browser and without signing in. Only the app's public client id is sent, as in a login."""
    reg = REGISTRY[provider]
    q = {"client_id": client_id, "redirect_uri": redirect, "response_type": "code",
         "scope": scopes, "state": secrets.token_hex(32),
         "code_challenge": secrets.token_urlsafe(32), "code_challenge_method": "S256"}
    try:
        status, location = (get or _get_no_follow)(
            reg["authorize"] + "?" + urllib.parse.urlencode(q))
    except OSError as e:
        return "network_error", str(e)[:200]
    return classify_authorize(status, location, redirect)


def preflight(provider: str, home: Path | None = None, port: int | None = None,
              probe: bool = True, get: Any = None,
              creds: tuple[str, str] | None = None) -> dict[str, Any]:
    """Everything that can be checked before the browser opens. ``ready`` is False when the
    sign-in cannot succeed; ``next`` is the one thing to do."""
    if provider not in REGISTRY:
        raise ValueError(f"no connection doctor for {provider!r} yet; known: "
                         + ", ".join(REGISTRY))
    reg = REGISTRY[provider]
    port = port or reg["port"]
    redirect = redirect_for(provider, port)
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool | None, detail: str, fix: str = "") -> None:
        checks.append({"check": name, "ok": ok, "detail": detail,
                       **({"fix": fix} if fix and ok is False else {})})

    import importlib
    mod = importlib.import_module(f"bau.{reg['module']}")
    check("callback_handler", callable(getattr(mod, "login", None)) and bool(reg["path"]),
          f"bau.{reg['module']}.login answers {reg['path']}",
          "BAU is incomplete: reinstall (sudo bau update now)")
    if creds is None:
        try:
            creds = mod.app_credentials()
        except Exception:  # noqa: BLE001 - the module's own error names the keys
            creds = None
    check("app_keys", creds is not None,
          "present" if creds else f"{' and '.join(reg['keys'])} missing",
          f"sudo bau keys set {' '.join(reg['keys'])}")
    free, why = port_check(port)
    check("port", free, why, why)
    check("redirect", True, f"BAU sends {redirect} (exact, in the login and the token "
          "exchange)")
    good = known_good(provider, home)
    if good and good.get("redirect") != redirect:
        check("redirect_vs_last_working", False,
              f"last verified with {good['redirect']} on {good['verified_at']}, now {redirect}",
              f"use --port {good.get('port')} or register {redirect}: {reg['register_at']}")
    scopes = getattr(mod, "SCOPES", "")
    if probe and reg.get("probe") and creds:
        verdict, why = probe_authorize(provider, creds[0], redirect, scopes, get)
        fixes = {"redirect_not_registered": f"register exactly {redirect} at: "
                                            f"{reg['register_at']}",
                 "unknown_client": f"{reg['keys'][0]} is not an app {provider} knows: copy "
                                   "the client id again (sudo bau keys set ...)",
                 "network_error": "check the internet connection, then try again"}
        check("platform_accepts_redirect",
              None if verdict == "network_error" else verdict == "ok",
              verdict + (f": {why}" if why else ""), fixes.get(verdict, "see docs: "
                                                               + reg["docs"][0]))
    elif probe and not reg.get("probe"):
        check("platform_accepts_redirect", None,
              f"not probed ({provider}'s answer to a probe is unverified): the redirect must "
              f"match exactly what is registered at: {reg['register_at']}")
    failed = [c for c in checks if c["ok"] is False]
    return {"provider": provider, "ready": not failed, "redirect": redirect, "port": port,
            "scopes": scopes, "checks": checks,
            "next": failed[0]["fix"] if failed else f"bau {provider} login"}


# ------------------------------------------------------------------ state

def state(provider: str, home: Path | None = None) -> dict[str, Any]:
    """One of STATES with why. API_VERIFIED needs a real API answer recorded after the
    current sign-in; finishing the consent page is only AUTHENTICATED."""
    reg = REGISTRY[provider]
    import importlib
    mod = importlib.import_module(f"bau.{reg['module']}")
    try:
        mod.app_credentials()
        keys = True
    except Exception:  # noqa: BLE001
        keys = False
    store = mod.TokenStore(home).store
    sign_in = store.state()
    out: dict[str, Any] = {"provider": provider, "keys": keys, "sign_in": sign_in}
    recs = last_attempt(provider, home)
    last = recs[-1] if recs else None
    if sign_in == "unreadable":
        return {**out, "state": "CONFIGURATION_ERROR",
                "why": "the sign-in exists but this account cannot read it"}
    if sign_in == "missing":
        if not keys:
            return {**out, "state": "NOT_CONFIGURED", "why": "app keys missing"}
        if last and not last["ok"]:
            st = ("PERMISSION_DENIED" if "access_denied" in json.dumps(last) else
                  "NETWORK_ERROR" if last["stage"] == "preflight" and
                  "network" in json.dumps(last) else "NEEDS_OWNER_ACTION")
            return {**out, "state": st, "why": f"last attempt failed at {last['stage']}",
                    "next": last.get("next", f"bau connect doctor {provider}")}
        return {**out, "state": "READY_TO_AUTHORIZE", "why": "keys present, not signed in"}
    tok = mod.TokenStore(home).load() or {}
    now = time.time()
    if tok.get("refresh_expires_at") and now >= float(tok["refresh_expires_at"]):
        return {**out, "state": "EXPIRED", "why": "the refresh token expired: sign in again"}
    missing = scope_diff(getattr(mod, "SCOPES", ""), tok.get("scope", ""), reg["scope_sep"])
    if missing:
        out["missing_scopes"] = missing
    if last and last["stage"] == "api_check" and not last["ok"]:
        code = int(last.get("http_status") or 0)
        err = str(last.get("error", ""))
        st = ("REVOKED" if code == 401 or "invalid_grant" in err or "login failed" in err
              else "PERMISSION_DENIED" if code == 403 else
              "NETWORK_ERROR" if not code else "PROVIDER_ERROR")
        return {**out, "state": st, "why": last.get("error", "the API check failed"),
                "next": last.get("next", f"bau connect doctor {provider}")}
    # Proven only by an API answer recorded after the latest sign-in (a newer sign-in is a
    # newer attempt whose last stage is "stored" until its own API check ran).
    verified = bool(last and last["stage"] == "api_check" and last["ok"])
    if now >= float(tok.get("access_expires_at") or 0):
        return {**out, "state": "REFRESH_REQUIRED" if tok.get("refresh_token") else "EXPIRED",
                "why": "access token expired" + (": renewed on next use"
                                                 if tok.get("refresh_token") else "")}
    if missing:
        return {**out, "state": "PERMISSION_DENIED",
                "why": "granted without " + ", ".join(missing)}
    if verified:
        return {**out, "state": "API_VERIFIED", "why": f"{reg['health']} answered at "
                f"{last['at']}"}
    return {**out, "state": "AUTHENTICATED",
            "why": f"signed in; not yet proven by an API call: bau {provider} status --check"}


def record_api_check(provider: str, home: Path | None, ok: bool, via: str = "terminal",
                     account: str | None = None, error: str = "", http_status: int = 0,
                     rec: Recorder | None = None) -> None:
    rec = rec or Recorder(provider, home, via)
    if ok:
        rec.stage("api_check", True, account=account)
    else:
        nxt = (f"bau {provider} login (the platform no longer accepts this sign-in)"
               if http_status == 401 else
               "the app lacks a permission: check its scopes on the platform"
               if http_status == 403 else f"bau connect doctor {provider}")
        rec.stage("api_check", False, http_status=http_status, error=error[:300], next=nxt)


def http_status_of(err: Exception) -> int:
    m = re.search(r"HTTP (\d{3})", str(err))
    return int(m.group(1)) if m else 0


# ------------------------------------------------------------------ report

def report(provider: str, home: Path | None = None, pre: dict[str, Any] | None = None) -> str:
    """A plain-text report to paste anywhere (to Claude, to support). No secrets in it."""
    reg = REGISTRY[provider]
    st = state(provider, home)
    lines = [f"BAU connection report: {provider} ({dt.date.today().isoformat()})",
             f"state: {st['state']} - {st.get('why', '')}",
             f"authorize: {reg['authorize']}", f"token: {reg['token']}",
             f"callback: {redirect_for(provider)} (listener 127.0.0.1:{reg['port']}, only "
             "while a sign-in waits)",
             f"register at: {reg['register_at']}"]
    if st.get("missing_scopes"):
        lines.append("missing scopes: " + ", ".join(st["missing_scopes"]))
    if pre:
        lines.append("pre-flight:")
        for c in pre["checks"]:
            mark = {True: "ok  ", False: "FAIL", None: "?   "}[c["ok"]]
            lines.append(f"  [{mark}] {c['check']}: {c['detail']}"
                         + (f"\n         fix: {c['fix']}" if c.get("fix") else ""))
    recs = last_attempt(provider, home)
    if recs:
        lines.append(f"last attempt {recs[0]['attempt']} via {recs[0].get('via')}:")
        for r in recs:
            extra = {k: v for k, v in r.items() if k not in
                     ("provider", "attempt", "via", "at", "stage", "ok")}
            lines.append(f"  {r['at']} {r['stage']}: {'ok' if r['ok'] else 'FAILED'} "
                         + json.dumps(extra, default=str)[:300])
    good = known_good(provider, home)
    if good:
        lines.append(f"last verified: {good['verified_at']} with {good['redirect']}")
    if st.get("next"):
        lines.append(f"next: {st['next']}")
    lines.append("docs: " + " ; ".join(reg["docs"]))
    return redact("\n".join(lines))
