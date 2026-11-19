"""Fanvue: post the creator's pictures (the owner's Accept posts each) and bring the earnings
into BAU's ledger (docs/FANVUE.md).

The machine prepares everything: the picture (drawn here, age-checked, with provenance), the
caption with the AI label, the level. Jarvis puts one card on the owner's screen; the owner
picks the audience (no default) and presses Accept, and only then is it uploaded and posted.
No agent, model or the Governor can post on its own.

API facts verified 2026-11-03 against api.fanvue.com/docs (authentication/overview,
authentication/implementation-guide, authentication/scopes, authentication/rate-limits,
tutorials/uploading-media, v1/api-reference pages for each path below):
  Auth   OAuth 2.0 authorization code + PKCE (S256, required); no API keys, no personal tokens.
         https://auth.fanvue.com/oauth2/auth (client_id, redirect_uri, response_type=code,
         scope space-separated, state >= 32 chars, code_challenge, code_challenge_method=S256);
         token https://auth.fanvue.com/oauth2/token, client_secret_basic (HTTP Basic
         client_id:client_secret), form body. `expires_in` per response (no fixed lifetime);
         refresh tokens need offline_access, ROTATE and are single-use: always keep the new one.
         System scopes openid, offline_access, offline: request them on an API-only app.
         The redirect URI must match one registered on the app's Authentication tab exactly.
         Read 2026-11-15: Fanvue's developer docs allow http://127.0.0.1 redirect addresses;
         it must match exactly and the app must be saved. A wrong one shows Fanvue's own
         page "invalid_request ... redirect_uri" and never calls back, so BAU only times out.
  Header X-Fanvue-API-Version: 2025-06-26 on every call.
  Me     GET /v1/users/me (read:self): uuid, handle, displayName, isCreator, isAiCreator.
  Upload POST /v1/media/uploads {name, filename, mediaType image|video|audio|document,
         sizeBytes} -> mediaUuid, uploadId, partSize, totalParts (write:media);
         GET /v1/creators/{creatorUserUuid}/media/uploads/{uploadId}/parts/urls?from=1&to=N
         -> parts [{partNumber, url}] (write:creator + write:media, to <= 256);
         PUT raw bytes to each url with NO Authorization header, keep each ETag;
         PATCH /v1/media/uploads/{uploadId} {parts: [{PartNumber, ETag}]} -> processing;
         GET /v1/media/{uuid} (read:media) status created|processing|ready|error, errorReason.
         Attach only once status is "ready". Max file 1.5 GiB.
  Post   POST /v1/posts (write:post): audience "subscribers" | "followers-and-subscribers"
         (required), text (<= 5000, checked for prohibited language), mediaUuids, price (USD
         cents, >= 300, needs media), publishAt, expiresAt -> uuid, publishAt, publishedAt.
  Money  GET /v1/insights/earnings (read:insights): startDate, endDate (exclusive), cursor,
         size 1-50 -> data [{date, gross, net, total (USD cents), source, transactionOrderId,
         transactionOrderStatus, ...}], nextCursor. Refunds/chargebacks are their own rows
         with negative amounts.
  Limits 200 requests / 60 s per client per user, 6 in flight; 429 with Retry-After.
  AI     No API field for an AI label. Fanvue's own rule (help.fanvue.com, read 2026-11-01,
         examples/platform-fanvue.yaml): AI media disclosed clearly (bio, caption or
         watermark). BAU puts the label in every caption.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import math
import os
import secrets
import time
import urllib.parse
from pathlib import Path
from typing import Any

from .audit import AuditLog
from .credentials import CredentialError, Store, fix_command
from .home import atomic_write_json, bau_home
from .tiktok import Http, TikTokError, _env_file, oauth_callback

API = "https://api.fanvue.com"
AUTH_URL = "https://auth.fanvue.com/oauth2/auth"
TOKEN_URL = "https://auth.fanvue.com/oauth2/token"
VERSION = "2025-06-26"
SCOPES = ("openid offline_access offline read:self read:media write:media write:creator "
          "write:post read:insights")
PORT = 3456
AUDIENCES = {"subscribers": "Subscribers only",
             "followers-and-subscribers": "Followers and subscribers"}
AI_LABEL = "AI-generated: a fictional AI character, not a real person."
LEVELS = {0: "teaser (free, sfw)", 1: "subscriber (no nudity)", 2: "nude unlock",
          3: "xxx unlock"}
MIN_PRICE_CENTS = 300                    # POST /v1/posts price: USD cents, >= 300, needs media
IMAGE_TYPES = {".png", ".jpg", ".jpeg"}


class FanvueError(RuntimeError):
    pass


def pkce_pair() -> tuple[str, str]:
    """RFC 7636 S256: base64url(SHA-256(verifier)) without padding."""
    verifier = secrets.token_urlsafe(64)[:96]
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def app_credentials(env_file: Path = Path("/etc/bau/platforms.env")) -> tuple[str, str]:
    env = {**_env_file(env_file), **os.environ}
    cid, secret = env.get("FANVUE_CLIENT_ID"), env.get("FANVUE_CLIENT_SECRET")
    if not cid or not secret:
        raise FanvueError("set FANVUE_CLIENT_ID and FANVUE_CLIENT_SECRET (on the desktop, "
                          "headquarters: /etc/bau/platforms.env, via bau keys import)")
    return cid, secret


class TokenStore:
    """BAU_HOME/secrets/fanvue.json in the one shared credential store (credentials.py): the
    owner's login, Jarvis and the autopilot read the same sign-in. Never logged."""

    def __init__(self, home: Path | None = None):
        self.store = Store("fanvue", home)
        self.path = self.store.path

    def load(self) -> dict[str, Any] | None:
        return self.store.load()

    def save(self, tok: dict[str, Any]) -> None:
        try:
            old = self.load() or {}
        except CredentialError:
            old = {}
        self.store.save({
            "access_token": tok["access_token"],
            # rotating, single-use: the new one replaces the old one every time
            "refresh_token": tok.get("refresh_token") or old.get("refresh_token", ""),
            "scope": tok.get("scope", old.get("scope", "")),
            "access_expires_at": time.time() + int(tok.get("expires_in") or 0) - 60})

    def clear(self) -> None:
        self.store.clear()


class FanvueClient:
    def __init__(self, home: Path | None = None, http: Any = None,
                 creds: tuple[str, str] | None = None, sleep: Any = time.sleep):
        self.tokens = TokenStore(home)
        self.http = http or FanvueHttp()
        self._creds = creds
        self.sleep = sleep

    @property
    def creds(self) -> tuple[str, str]:
        if self._creds is None:
            self._creds = app_credentials()
        return self._creds

    # -------------------------------------------------------- OAuth
    def authorize_url(self, redirect_uri: str, state: str, challenge: str) -> str:
        q = {"client_id": self.creds[0], "redirect_uri": redirect_uri, "response_type": "code",
             "scope": SCOPES, "state": state, "code_challenge": challenge,
             "code_challenge_method": "S256"}
        return AUTH_URL + "?" + urllib.parse.urlencode(q)

    def _token(self, form: dict[str, str]) -> dict[str, Any]:
        basic = base64.b64encode(f"{self.creds[0]}:{self.creds[1]}".encode()).decode()
        code, raw = self.http.request("POST", TOKEN_URL, {
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded"},
            urllib.parse.urlencode(form).encode())
        data = json.loads(raw or b"{}")
        if code != 200 or "access_token" not in data:
            raise FanvueError(f"Fanvue login failed: {data.get('error_description') or code}"
                              " - connect again: bau fanvue login")
        self.tokens.save(data)
        return data

    def exchange(self, code: str, redirect_uri: str, verifier: str) -> dict[str, Any]:
        return self._token({"grant_type": "authorization_code", "code": code,
                            "redirect_uri": redirect_uri, "code_verifier": verifier})

    def connected(self) -> bool:
        return self.tokens.store.state() == "present"

    def _load(self) -> dict[str, Any]:
        try:
            tok = self.tokens.load()
        except CredentialError as e:
            raise FanvueError(str(e)) from None
        if tok is None:
            raise FanvueError("Fanvue is not connected: bau fanvue login")
        return tok

    def access_token(self) -> str:
        tok = self._load()
        if time.time() < tok["access_expires_at"]:
            return tok["access_token"]
        # The refresh token works once: Jarvis and the autopilot must not both spend it.
        with self.tokens.store.refresh_lock():
            tok = self._load()                    # another process may have just refreshed
            if time.time() < tok["access_expires_at"]:
                return tok["access_token"]
            return self._token({"grant_type": "refresh_token",
                                "refresh_token": tok["refresh_token"]})["access_token"]

    # -------------------------------------------------------- API
    def call(self, method: str, path: str, payload: dict[str, Any] | None = None
             ) -> dict[str, Any]:
        for attempt in range(3):
            code, raw = self.http.request(method, API + path, {
                "Authorization": f"Bearer {self.access_token()}",
                "X-Fanvue-API-Version": VERSION, "Content-Type": "application/json"},
                json.dumps(payload).encode() if payload is not None else None)
            if code == 429 and attempt < 2:          # honour Fanvue's limit, then try again
                self.sleep(2 * (attempt + 1))
                continue
            break
        data = json.loads(raw or b"{}") if raw else {}
        if code >= 400:
            why = data.get("errors") or data.get("error") or data.get("message") or code
            raise FanvueError(f"Fanvue {method} {path.split('?')[0]}: HTTP {code} {why}"[:400])
        return data

    def me(self) -> dict[str, Any]:
        return self.call("GET", "/v1/users/me")

    def upload_image(self, path: Path, poll: int = 30) -> str:
        """The picture's mediaUuid once Fanvue says it is ready."""
        body = path.read_bytes()
        s = self.call("POST", "/v1/media/uploads", {"name": path.stem, "filename": path.name,
                                                    "mediaType": "image",
                                                    "sizeBytes": len(body)})
        part = int(s["partSize"])
        total = int(s.get("totalParts") or math.ceil(len(body) / part))
        me = self.me()["uuid"]
        urls = self.call("GET", f"/v1/creators/{me}/media/uploads/{s['uploadId']}/parts/urls"
                                f"?from=1&to={total}")["parts"]
        parts = []
        for p in sorted(urls, key=lambda p: p["partNumber"]):
            n = int(p["partNumber"])
            chunk = body[(n - 1) * part:n * part]
            code, etag = self.http.put_part(p["url"], chunk)   # no Authorization header
            if code >= 300 or not etag:
                raise FanvueError(f"part {n}/{total} was not accepted (HTTP {code})")
            parts.append({"PartNumber": n, "ETag": etag})
        self.call("PATCH", f"/v1/media/uploads/{s['uploadId']}", {"parts": parts})
        for _ in range(poll):
            m = self.call("GET", f"/v1/media/{s['mediaUuid']}")
            if m.get("status") == "ready":
                return s["mediaUuid"]
            if m.get("status") == "error":
                raise FanvueError(f"Fanvue could not use the picture: {m.get('errorReason')}")
            self.sleep(2)
        raise FanvueError("Fanvue is still processing the picture; try again in a minute")

    def create_post(self, text: str, audience: str, media: list[str],
                    price: int | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"text": text, "audience": audience, "mediaUuids": media}
        if price is not None:                     # an unlock: USD cents, >= 300, needs media
            body["price"] = int(price)
        return self.call("POST", "/v1/posts", body)

    def earnings(self, start: str, end: str) -> list[dict[str, Any]]:
        rows, cursor = [], None
        while True:
            q = {"startDate": start, "endDate": end, "size": 50, **({"cursor": cursor}
                                                                    if cursor else {})}
            page = self.call("GET", "/v1/insights/earnings?" + urllib.parse.urlencode(q))
            rows += page.get("data") or []
            cursor = page.get("nextCursor")
            if not cursor:
                return rows


class FanvueHttp(Http):
    def put_part(self, url: str, body: bytes) -> tuple[int, str]:
        """PUT raw bytes to a signed upload URL (no Authorization header); its ETag."""
        import urllib.error
        import urllib.request
        req = urllib.request.Request(url, data=body, method="PUT")
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                return r.status, r.headers.get("ETag", "")
        except urllib.error.HTTPError as e:
            return e.code, ""


def status(home: Path | None = None, client: FanvueClient | None = None,
           check: bool = False) -> dict[str, Any]:
    """The one answer to "is Fanvue connected", the same for the terminal, Jarvis, bau money
    and the autopilot, because all of them read the one shared store. Nothing secret: no
    token, code or key is ever in it. ``check`` asks Fanvue who the account is (a real call)."""
    home = home or bau_home()
    try:
        app_credentials()
        keys = "on this computer"
    except FanvueError:
        keys = "missing"
    tokens = TokenStore(home)
    sign_in = tokens.store.state()
    out: dict[str, Any] = {"app_keys": keys, "sign_in": sign_in, "store": str(tokens.path),
                           "connected": sign_in == "present"}
    if sign_in == "present":
        tok = tokens.load() or {}
        left = float(tok.get("access_expires_at", 0)) - time.time()
        out["access"] = (f"valid for {int(left // 60)} more minutes" if left > 0 else
                         "expired: renewed on its next use" if tok.get("refresh_token") else
                         "expired and cannot be renewed: bau fanvue login")
    elif sign_in == "unreadable":
        out["fix"] = fix_command(tokens.path)
    else:
        out["fix"] = ("sudo bau keys set FANVUE_CLIENT_ID FANVUE_CLIENT_SECRET, then "
                      "bau fanvue login") if keys == "missing" else "bau fanvue login"
    if check and sign_in == "present":
        try:
            me = (client or FanvueClient(home)).me()
            out["account"] = me.get("handle")
        except (FanvueError, OSError) as e:
            out["connected"] = False
            out["check_failed"] = str(e)[:300]
    return out


def redirect_hint(redirect: str) -> str:
    """What to do when Fanvue's own page says invalid_request / redirect_uri."""
    return (f"If Fanvue showed invalid_request or redirect_uri, register exactly {redirect} "
            "on your Fanvue app's Authentication tab and press Save, then run the login again.")


def login(client: FanvueClient, port: int = PORT, open_browser: Any = None,
          timeout: int = 300, rec: Any = None) -> dict[str, Any]:
    """A callback server on 127.0.0.1. Register http://127.0.0.1:<port>/callback as a
    redirect URI on the Fanvue app's Authentication tab. The browser says "connected" only
    once the token is saved on this computer (oauth_callback). The address is printed before
    the browser opens, and a refusal or a timeout repeats it (the owner's login, 2026-11-18)."""
    redirect = f"http://127.0.0.1:{port}/callback"
    verifier, challenge = pkce_pair()
    state = secrets.token_hex(32)
    from .integrations import Recorder
    rec = rec or Recorder("fanvue", client.tokens.path.parent.parent)
    stage = rec.stage

    def finish(got: dict[str, str]) -> dict[str, Any]:
        state_ok = secrets.compare_digest(got.get("state", ""), state)
        stage("callback", state_ok and "code" in got, state_valid=state_ok,
              code_received="code" in got, provider_error=got.get("error"),
              provider_error_description=got.get("error_description"))
        if not state_ok:
            raise FanvueError("state mismatch - login aborted")
        if "code" not in got:
            raise FanvueError("Fanvue refused: "
                              f"{got.get('error_description') or got.get('error')}\n"
                              + redirect_hint(redirect))
        try:
            tok = client.exchange(got["code"], redirect, verifier)
        except FanvueError as e:      # the callback was fine: the token exchange failed
            stage("token_exchange", False, error=str(e)[:300], redirect=redirect,
                  next="invalid_grant = code used/expired or PKCE mismatch: sign in again; "
                       "invalid_client = check FANVUE_CLIENT_SECRET")
            raise
        except OSError as e:          # the token could not be written in BAU_HOME/secrets
            stage("stored", False, error=str(e)[:300])
            raise FanvueError(f"Fanvue answered, but the login could not be saved in "
                              f"{client.tokens.path}: {e}") from e
        stage("token_exchange", True, granted_scopes=tok.get("scope", ""))
        if client.tokens.load() is None:
            stage("stored", False, error="not saved")
            raise FanvueError(f"the login was not saved in {client.tokens.path}")
        stage("stored", True, store=str(client.tokens.path))
        return tok

    url = client.authorize_url(redirect, state, challenge)
    print(f"Fanvue sends you back to {redirect}\nRegister exactly that address on your "
          "Fanvue app's Authentication tab and press Save.")
    stage("authorize_url", True, redirect=redirect, port=port, scopes=SCOPES)
    try:
        return oauth_callback("Fanvue", port, "/callback", url,
                              open_browser or (lambda u: print(f"Open this link to connect "
                                                               f"Fanvue:\n{u}")),
                              timeout, finish)
    except TikTokError as e:          # the shared helper's timeout
        stage("callback", False, error=str(e), redirect=redirect,
              next=redirect_hint(redirect) + " Or the browser was not on this computer.")
        raise FanvueError(f"{e}\n{redirect_hint(redirect)}") from None
    except OSError as e:              # the listener could not start
        stage("listener", False, error=str(e)[:200], port=port,
              next=f"port {port} busy: ss -ltnp 'sport = :{port}'")
        raise


# ------------------------------------------------------------------ the queue

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Queue:
    """BAU_HOME/fanvue/queue/ITEM.json: a picture from artifacts/media and its caption."""

    def __init__(self, home: Path | None = None, audit: AuditLog | None = None):
        self.home = home or bau_home()
        self.dir = self.home / "fanvue" / "queue"
        self.audit = audit or AuditLog(self.home / "audit" / "chain.jsonl")

    def items(self) -> list[dict[str, Any]]:
        if not self.dir.is_dir():
            return []
        items = [json.loads(p.read_text()) for p in self.dir.glob("fv_*.json")]
        return sorted(items, key=lambda i: (i["queued_at"], i["item_id"]))   # oldest first

    def pending(self) -> list[dict[str, Any]]:
        return [i for i in self.items() if i["status"] == "QUEUED"]

    def review(self) -> list[dict[str, Any]]:
        """Drafted by the autopilot, waiting for the owner's Accept before it can post."""
        return [i for i in self.items() if i["status"] == "REVIEW"]

    def decide(self, item_id: str, approve: bool, by: str) -> dict[str, Any]:
        if not by.startswith("human:"):
            raise PermissionError("only the owner approves a picture")
        item = self.get(item_id)
        if item is None or item["status"] != "REVIEW":
            raise FanvueError(f"{item_id} is not waiting for review")
        if approve and _sha256(self.picture(item)) != item["picture_sha256"]:
            raise FanvueError("the picture changed after it was drafted")
        item["status"] = "QUEUED" if approve else "DROPPED"
        item["reviewed_by"], item["reviewed_at"] = by, dt.datetime.now(dt.UTC).isoformat()
        self.save(item)
        self.audit.append("fanvue.approved" if approve else "fanvue.dropped", by,
                          {"item": item_id})
        return item

    def get(self, item_id: str) -> dict[str, Any] | None:
        return next((i for i in self.items() if i["item_id"] == item_id), None)

    def save(self, item: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.dir / f"{item['item_id']}.json", item)

    def picture(self, item: dict[str, Any]) -> Path:
        return self.home / "artifacts" / "media" / item["picture"]

    def check(self, picture: str, caption: str, level: int,
              price_cents: int | None = None) -> list[str]:
        from .virtual_creator import MINOR_REFERENCE
        problems = []
        if level not in LEVELS:
            problems.append("the level is 0, 1, 2 or 3")
        if level >= 2 and (price_cents is None or price_cents < MIN_PRICE_CENTS):
            problems.append("a level 2 or 3 unlock needs your price ($3.00 or more)")
        if MINOR_REFERENCE.search(caption):
            problems.append("the caption refers to minors or youth-coded words")
        p = self.home / "artifacts" / "media" / Path(picture).name
        if Path(picture).name != picture or p.suffix.lower() not in IMAGE_TYPES \
                or not p.is_file():
            problems.append("the picture must be a file in artifacts/media (bau creator draw)")
            return problems
        try:
            prov = json.loads(p.with_name(p.name + ".provenance.json").read_text())
        except (OSError, ValueError):
            prov = {}
        if not (prov.get("ai_generated") and (prov.get("age_check") or {}).get("passed")):
            problems.append("the picture has no provenance record with a passed age check")
        elif prov.get("file_sha256") != _sha256(p):
            problems.append("the picture changed after it was checked")
        elif level >= 2 and prov.get("lane") != "explicit":
            problems.append("levels 2 and 3 take only pictures from the explicit lane")
        return problems

    def add(self, picture: str, caption: str, level: int, by: str,
            review: bool = False, price_cents: int | None = None) -> dict[str, Any]:
        caption = caption.strip()
        if AI_LABEL not in caption:                  # Fanvue's rule and BAU's: always on
            caption = f"{caption}\n\n{AI_LABEL}".strip()
        problems = self.check(picture, caption, level, price_cents)
        if len(caption) > 5000:
            problems.append("the caption is longer than Fanvue's 5000 characters")
        if problems:
            raise ValueError("; ".join(problems))
        item = {"item_id": "fv_" + secrets.token_hex(5), "picture": picture,
                "caption": caption, "level": level, "status": "REVIEW" if review else "QUEUED",
                "price_cents": price_cents if level >= 2 else None,
                "picture_sha256": _sha256(self.home / "artifacts" / "media" / picture),
                "queued_by": by, "queued_at": dt.datetime.now(dt.UTC).isoformat(),
                "result": {}}
        self.save(item)
        self.audit.append("fanvue.queued", by, {"item": item["item_id"], "level": level})
        return item

    def post(self, item: dict[str, Any], client: FanvueClient, approver: str,
             audience: str) -> dict[str, Any]:
        """Called only after the owner's Accept on the card."""
        if not approver.startswith("human:"):
            raise PermissionError("only the owner posts to Fanvue")
        from .governor import hold_reason
        if (why := hold_reason(self.home)) is not None:
            raise FanvueError(f"BAU is on HOLD ({why}): nothing is posted until it is released")
        if item["status"] != "QUEUED":
            raise FanvueError(f"{item['item_id']} is {item['status']}; it is posted only once")
        if audience not in AUDIENCES:
            raise FanvueError("the owner must choose the audience")
        if problems := self.check(item["picture"], item["caption"], item["level"],
                                  item.get("price_cents")):
            raise FanvueError("; ".join(problems))
        if _sha256(self.picture(item)) != item["picture_sha256"]:
            raise FanvueError("the picture changed since it was queued - queue it again")
        item["status"] = "POSTING"                   # never twice, even if the next step fails
        self.save(item)
        try:
            media = client.upload_image(self.picture(item))
            out = client.create_post(item["caption"], audience, [media],
                                     price=item.get("price_cents"))
        except Exception as e:
            item["status"], item["result"] = "FAILED", {"error": str(e)[:300]}
            self.save(item)
            self.audit.append("fanvue.failed", approver, {"item": item["item_id"]})
            raise
        item["status"] = "POSTED"
        item["result"] = {"post_uuid": out.get("uuid"), "published_at": out.get("publishedAt"),
                          "audience": audience}
        self.save(item)
        self.audit.append("fanvue.posted", approver, {"item": item["item_id"],
                                                      "post": out.get("uuid"),
                                                      "audience": audience})
        return item


# ------------------------------------------------------------------ earnings into the ledger

SYNC_EVERY_S = 3600


def sync_earnings(home: Path, client: FanvueClient, now: dt.datetime | None = None,
                  days: int = 30) -> dict[str, Any]:
    """Every Fanvue earning row once into economics/revenue.jsonl (gross, Fanvue's cut as the
    platform fee, refunds and chargebacks as refunds). Rows already recorded are skipped."""
    from .economics import Ledger
    now = now or dt.datetime.now(dt.UTC)
    seen_path = home / "economics" / "fanvue_seen.json"
    seen = json.loads(seen_path.read_text()) if seen_path.exists() else {"ids": []}
    known = set(seen["ids"])
    start = (now - dt.timedelta(days=days)).isoformat(timespec="seconds")
    rows = client.earnings(start, now.isoformat(timespec="seconds"))
    ledger, added, usd = Ledger(home), 0, 0.0
    for r in rows:
        key = f"{r.get('transactionOrderId')}:{r.get('source')}:{r.get('gross')}"
        if key in known:
            continue
        gross, net = int(r.get("gross") or 0), int(r.get("net") or 0)
        when = dt.datetime.fromisoformat(str(r["date"]).replace("Z", "+00:00"))
        # a refund gives Fanvue's cut back too, so its fee counts negative
        ledger.sale(abs(gross) / 100, factory="fanvue", platform_fee=(gross - net) / 100,
                    refund=gross < 0, when=when)
        known.add(key)
        added += 1
        usd += net / 100
    seen = {"ids": sorted(known), "synced_at": now.isoformat(timespec="seconds")}
    seen_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(seen_path, seen)
    return {"new_rows": added, "net_usd": round(usd, 2), "synced_at": seen["synced_at"]}


def sync_if_due(home: Path, client: FanvueClient | None = None) -> dict[str, Any] | None:
    """For the money tool: at most once an hour, and only once Fanvue is connected."""
    client = client or FanvueClient(home)
    if not client.connected():
        return None
    seen_path = home / "economics" / "fanvue_seen.json"
    try:
        last = dt.datetime.fromisoformat(json.loads(seen_path.read_text())["synced_at"])
        if (dt.datetime.now(dt.UTC) - last).total_seconds() < SYNC_EVERY_S:
            return None
    except (OSError, ValueError, KeyError):
        pass
    return sync_earnings(home, client)


# ------------------------------------------------------------------ autopost (the owner's switch)
# The owner's choice (2026-11-03, "let Jarvis be Jarvis"): once he switches it on, with the
# audience and the number a day he picks (no defaults), the autopilot posts queued Fanvue
# posts by itself. Every content check still runs on each post; HOLD stops it.
MAX_PER_DAY = 10


def autopost_choice(home: Path) -> dict[str, Any] | None:
    p = home / "fanvue" / "autopost.json"
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def set_autopost(home: Path, on: bool, by: str, audience: str = "",
                 per_day: int = 0) -> dict[str, Any]:
    if not by.startswith("human:"):
        raise PermissionError("only the owner switches autopost")
    if on and (audience not in AUDIENCES or not 1 <= int(per_day) <= MAX_PER_DAY):
        raise ValueError(f"choose the audience and 1 to {MAX_PER_DAY} posts a day")
    rec = {"on": on, "audience": audience if on else "", "per_day": int(per_day) if on else 0,
           "by": by, "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}
    (home / "fanvue").mkdir(parents=True, exist_ok=True)
    atomic_write_json(home / "fanvue" / "autopost.json", rec)
    AuditLog(home / "audit" / "chain.jsonl").append("fanvue.autopost", by,
                                                    {k: rec[k] for k in ("on", "audience",
                                                                         "per_day")})
    return rec


def autopost_tick(home: Path, client: FanvueClient | None = None,
                  now: dt.datetime | None = None) -> dict[str, Any]:
    """One post at most per run of the autopilot (every 30 min), within the owner's number a
    day. A failure today stops it until tomorrow, so a broken login does not burn the queue."""
    from .station import is_station
    if is_station():                      # the laptop: the desktop's money machine posts
        return {"autopost": "off (this laptop is the station; the desktop posts)"}
    choice = autopost_choice(home)
    if not choice or not choice.get("on"):
        return {"autopost": "off"}
    today = (now or dt.datetime.now(dt.UTC)).date().isoformat()
    q = Queue(home)
    mine = [i for i in q.items() if i.get("auto") and str(i.get("tried_at", "")).startswith(
        today)]
    if any(i["status"] == "FAILED" for i in mine):
        return {"autopost": "stopped for today after a failure", "item": mine[-1]["item_id"]}
    posted = sum(i["status"] == "POSTED" for i in mine)
    if posted >= choice["per_day"]:
        return {"autopost": "done for today", "posted_today": posted}
    waiting = q.pending()
    if not waiting:
        return {"autopost": "nothing queued", "posted_today": posted}
    from . import spatial  # God's Eye: the audience's evening, brand safety
    if not spatial.posting_time_ok(home, now or dt.datetime.now(dt.UTC)):
        return {"autopost": "waiting for the audience's evening", "posted_today": posted}
    pause = spatial.brand_pause_now(home)
    if pause:
        return {"autopost": f"held today for brand safety: {pause}", "posted_today": posted}
    item = waiting[0]
    item["auto"], item["tried_at"] = True, (now or dt.datetime.now(dt.UTC)).isoformat()
    q.save(item)
    try:
        done = q.post(item, client or FanvueClient(home), choice["by"], choice["audience"])
    except Exception as e:  # noqa: BLE001 - reported, and the day stops here
        cur = q.get(item["item_id"]) or item
        if cur["status"] == "QUEUED" and "HOLD" not in str(e):   # refused by a check
            cur["status"], cur["result"] = "FAILED", {"error": str(e)[:300]}
            q.save(cur)
        return {"autopost": "failed", "item": item["item_id"], "why": str(e)[:200]}
    return {"autopost": "posted", "item": done["item_id"], "posted_today": posted + 1}
