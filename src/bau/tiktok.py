"""TikTok: review-and-post (Content Posting API, Direct Post or inbox draft).

The machine prepares everything - video, caption, provenance, compliance checks -
and queues it. The owner runs ``bau tiktok review``: for each queued video it shows
what TikTok's Content Sharing Guidelines require (account nickname, preview,
privacy chosen with no default, commercial-content disclosure, Music Usage
Confirmation) and, on the owner's confirmation, uploads and posts it right away.
That confirmation is the express per-post consent TikTok requires; no agent, no
model and not the Governor can post on their own.

API facts verified 2026-10-05 against developers.tiktok.com:
  OAuth  https://www.tiktok.com/v2/auth/authorize/ (desktop: PKCE, hex SHA-256,
         redirect on localhost/127.0.0.1), token https://open.tiktokapis.com/v2/oauth/token/
         (access 24h, refresh 365d, refresh token may rotate)
  Post   /v2/post/publish/creator_info/query/, /v2/post/publish/video/init/ (video.publish),
         /v2/post/publish/inbox/video/init/ (video.upload, draft), /v2/post/publish/status/fetch/
  Upload PUT upload_url, Content-Range, chunks 5-64 MB (last up to 128 MB), files under
         5 MB in one chunk, total_chunk_count = floor(size / chunk_size), sequential.
  Unaudited apps: every post is private (SELF_ONLY) until TikTok audits the app.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import http.server
import json
import os
import secrets
import stat
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .audit import AuditLog, ref
from .home import atomic_write_json, bau_home
from .store import JsonlStore

API = "https://open.tiktokapis.com"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
SCOPES = "user.info.basic,video.publish,video.upload"
VIDEO_TYPES = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm"}
MB = 1024 * 1024
CHUNK = 10 * MB
MUSIC_CONFIRMATION = "By posting, you agree to TikTok's Music Usage Confirmation."
BRANDED_CONFIRMATION = ("By posting, you agree to TikTok's Branded Content Policy and "
                        "Music Usage Confirmation.")
PRIVACY_LABELS = {"PUBLIC_TO_EVERYONE": "Everyone", "MUTUAL_FOLLOW_FRIENDS": "Friends",
                  "FOLLOWER_OF_CREATOR": "Followers", "SELF_ONLY": "Only me"}


class TikTokError(RuntimeError):
    pass


def chunk_plan(size: int, chunk: int = CHUNK) -> tuple[int, int]:
    """(chunk_size, total_chunk_count) following TikTok's media transfer rules."""
    if size <= 0:
        raise TikTokError("empty video")
    if size > 4 * 1024 * MB:
        raise TikTokError("video larger than TikTok's 4 GB limit")
    if size < 5 * MB:
        return size, 1
    chunk = max(5 * MB, min(chunk, 64 * MB))
    if size <= chunk:
        return size, 1
    return chunk, size // chunk          # remainder rides in the last chunk


def pkce_pair() -> tuple[str, str]:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    verifier = "".join(secrets.choice(alphabet) for _ in range(64))
    return verifier, hashlib.sha256(verifier.encode()).hexdigest()   # TikTok: hex digest


# ------------------------------------------------------------------ credentials

class TokenStore:
    """Tokens live in BAU_HOME/secrets/tiktok.json, mode 0600. Never logged."""

    def __init__(self, home: Path | None = None):
        self.path = (home or bau_home()) / "secrets" / "tiktok.json"

    def load(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        return json.loads(self.path.read_text())

    def save(self, tok: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, stat.S_IRWXU)
        now = time.time()
        rec = {"access_token": tok["access_token"], "refresh_token": tok["refresh_token"],
               "open_id": tok.get("open_id", ""), "scope": tok.get("scope", ""),
               "access_expires_at": now + int(tok.get("expires_in", 0)) - 60,
               "refresh_expires_at": now + int(tok.get("refresh_expires_in", 0)) - 60}
        atomic_write_json(self.path, rec)
        os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


def _env_file(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return {}
    out = {}
    for line in lines:
        k, sep, v = line.strip().partition("=")
        if sep and not k.startswith("#"):
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def app_credentials(env_file: Path = Path("/etc/bau/platforms.env")) -> tuple[str, str]:
    env = {**_env_file(env_file), **os.environ}
    key, secret = env.get("TIKTOK_CLIENT_KEY"), env.get("TIKTOK_CLIENT_SECRET")
    if not key or not secret:
        raise TikTokError("set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET "
                          "(on the laptop: /etc/bau/platforms.env)")
    return key, secret


# ------------------------------------------------------------------ HTTP

class Http:
    """Tiny JSON/bytes transport; tests replace it."""

    def request(self, method: str, url: str, headers: dict[str, str],
                body: bytes | None = None, timeout: int = 120) -> tuple[int, bytes]:
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()


class TikTokClient:
    def __init__(self, home: Path | None = None, http: Http | None = None,
                 creds: tuple[str, str] | None = None):
        self.tokens = TokenStore(home)
        self.http = http or Http()
        self._creds = creds

    @property
    def creds(self) -> tuple[str, str]:
        if self._creds is None:
            self._creds = app_credentials()
        return self._creds

    # -------------------------------------------------------- OAuth
    def authorize_url(self, redirect_uri: str, state: str, challenge: str) -> str:
        q = {"client_key": self.creds[0], "scope": SCOPES, "response_type": "code",
             "redirect_uri": redirect_uri, "state": state, "code_challenge": challenge,
             "code_challenge_method": "S256"}
        return AUTH_URL + "?" + urllib.parse.urlencode(q)

    def _token(self, form: dict[str, str]) -> dict[str, Any]:
        key, secret = self.creds
        body = urllib.parse.urlencode({"client_key": key, "client_secret": secret,
                                       **form}).encode()
        code, raw = self.http.request("POST", API + "/v2/oauth/token/", {
            "Content-Type": "application/x-www-form-urlencoded"}, body)
        data = json.loads(raw or b"{}")
        if code != 200 or "access_token" not in data:
            raise TikTokError(f"token request failed: {data.get('error_description') or code}")
        self.tokens.save(data)
        return data

    def exchange(self, code: str, redirect_uri: str, verifier: str) -> dict[str, Any]:
        return self._token({"code": code, "grant_type": "authorization_code",
                            "redirect_uri": redirect_uri, "code_verifier": verifier})

    def access_token(self) -> str:
        tok = self.tokens.load()
        if tok is None:
            raise TikTokError("not connected: run `bau tiktok login`")
        if time.time() < tok["access_expires_at"]:
            return tok["access_token"]
        if time.time() >= tok["refresh_expires_at"]:
            raise TikTokError("TikTok login expired: run `bau tiktok login` again")
        return self._token({"grant_type": "refresh_token",
                            "refresh_token": tok["refresh_token"]})["access_token"]

    # -------------------------------------------------------- Content Posting API
    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        code, raw = self.http.request("POST", API + path, {
            "Authorization": f"Bearer {self.access_token()}",
            "Content-Type": "application/json; charset=UTF-8"}, json.dumps(payload).encode())
        data = json.loads(raw or b"{}")
        err = data.get("error") or {}
        if code != 200 or err.get("code", "ok") != "ok":
            raise TikTokError(f"{path}: {err.get('code', code)} {err.get('message', '')}"
                              .strip())
        return data.get("data") or {}

    def creator_info(self) -> dict[str, Any]:
        return self._post("/v2/post/publish/creator_info/query/", {})

    def init_upload(self, size: int, post_info: dict[str, Any] | None) -> dict[str, Any]:
        chunk, count = chunk_plan(size)
        source = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk,
                  "total_chunk_count": count}
        if post_info is None:              # inbox draft: the owner finishes in the app
            return self._post("/v2/post/publish/inbox/video/init/", {"source_info": source})
        return self._post("/v2/post/publish/video/init/",
                          {"post_info": post_info, "source_info": source})

    def upload(self, upload_url: str, video: Path) -> None:
        size = video.stat().st_size
        chunk, count = chunk_plan(size)
        ctype = VIDEO_TYPES[video.suffix.lower()]
        with video.open("rb") as fh:
            for i in range(count):
                start = i * chunk
                end = size - 1 if i == count - 1 else start + chunk - 1
                fh.seek(start)
                body = fh.read(end - start + 1)
                for attempt in range(3):
                    code, _ = self.http.request("PUT", upload_url, {
                        "Content-Range": f"bytes {start}-{end}/{size}",
                        "Content-Length": str(len(body)), "Content-Type": ctype}, body, 600)
                    if code in (201, 206):
                        break
                    if code < 500 or attempt == 2:
                        raise TikTokError(f"chunk {i + 1}/{count} rejected (HTTP {code})")
                    time.sleep(2 ** attempt)

    def status(self, publish_id: str) -> dict[str, Any]:
        return self._post("/v2/post/publish/status/fetch/", {"publish_id": publish_id})


def login(client: TikTokClient, port: int = 3455, open_browser: Any = None,
          timeout: int = 300) -> dict[str, Any]:
    """Desktop OAuth: a one-shot callback server on 127.0.0.1. Register
    http://127.0.0.1:<port>/callback/ as a redirect URI in the TikTok developer portal."""
    redirect = f"http://127.0.0.1:{port}/callback/"
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(24)
    got: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
            got.update(q)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"BAU: TikTok connected. You can close this tab.")

        def log_message(self, *a: Any) -> None:
            pass

    srv = http.server.HTTPServer(("127.0.0.1", port), Handler)
    srv.timeout = timeout
    url = client.authorize_url(redirect, state, challenge)
    (open_browser or (lambda u: print(f"Open this link to connect TikTok:\n{u}")))(url)
    srv.handle_request()
    srv.server_close()
    if not got:
        raise TikTokError("no answer from TikTok (timed out)")
    if not secrets.compare_digest(got.get("state", ""), state):
        raise TikTokError("state mismatch - login aborted")
    if "code" not in got:
        raise TikTokError(f"TikTok refused: {got.get('error_description') or got.get('error')}")
    return client.exchange(got["code"], redirect, verifier)


# ------------------------------------------------------------------ queue

@dataclass
class QueueItem:
    item_id: str
    video: str                         # path relative to BAU_HOME/artifacts
    caption: str
    is_aigc: bool = True
    created_at: str = ""
    created_by: str = ""
    status: str = "QUEUED"             # QUEUED | POSTED | DRAFTED | SKIPPED | REJECTED | FAILED
    checks: dict[str, Any] = field(default_factory=dict)
    publish_id: str = ""
    result: dict[str, Any] = field(default_factory=dict)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def duration_sec(video: Path) -> float | None:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", str(video)],
                             capture_output=True, text=True, timeout=30, check=False)
        return float(out.stdout.strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


class TikTokQueue:
    def __init__(self, home: Path | None = None, audit: AuditLog | None = None):
        self.home = home or bau_home()
        self.store = JsonlStore(self.home / "publish" / "tiktok" / "queue.jsonl")
        self.audit = audit or AuditLog(self.home / "audit" / "chain.jsonl")

    def items(self) -> list[QueueItem]:
        latest: dict[str, dict[str, Any]] = {}
        for r in self.store:
            latest[r["item_id"]] = r
        return [QueueItem(**r) for r in latest.values()]

    def pending(self) -> list[QueueItem]:
        return [i for i in self.items() if i.status == "QUEUED"]

    def save(self, item: QueueItem) -> None:
        self.store.append(asdict(item))

    def path(self, item: QueueItem) -> Path:
        return self.home / "artifacts" / item.video

    def add(self, video: Path, caption: str, by: str, is_aigc: bool | None = None,
            engine: Any = None) -> QueueItem:
        arts = (self.home / "artifacts").resolve()
        video = video.resolve()
        if not video.is_file() or not video.is_relative_to(arts):
            raise TikTokError("video must be a file inside BAU_HOME/artifacts")
        if video.suffix.lower() not in VIDEO_TYPES:
            raise TikTokError("TikTok accepts mp4, mov or webm")
        if len(caption.encode("utf-16-le")) // 2 > 2200:
            raise TikTokError("caption longer than TikTok's 2200 characters")
        item = QueueItem(item_id="tt_" + secrets.token_hex(5),
                         video=str(video.relative_to(arts)), caption=caption,
                         created_at=dt.datetime.now(dt.UTC).isoformat(), created_by=by)
        item.checks = self.check(item, is_aigc, engine)
        item.is_aigc = item.checks["is_aigc"]
        self.save(item)
        self.audit.append("tiktok.queued", by, {"item_id": item.item_id,
                                                "gate": item.checks["gate"]})
        return item

    def check(self, item: QueueItem, is_aigc: bool | None = None, engine: Any = None
              ) -> dict[str, Any]:
        """Everything that can be decided before the owner looks. BLOCKED never posts."""
        from .claims import scan
        from .disclosure import Provenance, check_publication
        from .platforms import PlatformRegistry
        video = self.path(item)
        problems: list[str] = []
        prov_path = video.with_suffix(video.suffix + ".provenance.json")
        prov = None
        if prov_path.exists():
            raw = json.loads(prov_path.read_text())
            if raw.get("artifact_sha256") and raw["artifact_sha256"] != _sha256(video):
                problems.append("video changed after its provenance record was written")
            prov = Provenance(**{k: v for k, v in raw.items()
                                 if k in Provenance.__dataclass_fields__})
        # No provenance record: AI unless the owner says it is human-made (--not-ai).
        ai = bool(prov.ai_generated or prov.synthetic_media) if prov else is_aigc is not False
        if is_aigc is False and ai:
            problems.append("provenance says AI-generated: the TikTok AI label cannot be "
                            "turned off")
        is_aigc = True if ai else bool(is_aigc)
        claims = scan(item.caption)
        if claims:
            problems.append("caption makes claims that need evidence: "
                            + ", ".join(c["claim_type"] for c in claims))
        plat = PlatformRegistry(self.home).facts("tiktok")
        if not plat["platform_policy_current"]:
            why = plat.get("reason") or f"{plat.get('policy_age_days')} days old"
            problems.append(f"TikTok policy record missing or stale ({why}): "
                            "bau platform add examples/platform-tiktok.yaml")
        gate = "UNKNOWN"
        if engine is not None:
            p = prov or (Provenance(item.item_id, "video", True, False, False, True,
                                    visible_disclosure_text="AI-GENERATED VIDEO") if ai
                         else Provenance(item.item_id, "video", False, False, True, False))
            d = check_publication(p, {"audience": [{"country": "US"}],
                                      "platform_requires_ai_label": True,
                                      "platform_label_set": is_aigc,
                                      "human_editorial_responsibility": True}, engine)
            gate = str(d.status)
            if gate not in ("PASS", "PASS_WITH_REVIEW", "NOT_APPLICABLE"):
                problems += [f["message"] for f in d.to_dict()["findings"]
                             if f["status"] not in ("PASS", "PASS_WITH_REVIEW",
                                                    "NOT_APPLICABLE")]
        return {"gate": gate, "is_aigc": is_aigc, "provenance": bool(prov),
                "problems": problems, "ok": not problems and gate != "UNKNOWN",
                "video_sha256": _sha256(video),
                "checked_at": dt.datetime.now(dt.UTC).isoformat()}

    # -------------------------------------------------------- the owner's click
    def post(self, item: QueueItem, client: TikTokClient, approver: str,
             privacy: str | None, options: dict[str, bool], creator: dict[str, Any],
             draft: bool = False, poll: int = 6) -> QueueItem:
        """Called only from the interactive review, after the owner confirmed."""
        if not approver.startswith("human:"):
            raise PermissionError("only a human at the review screen can post to TikTok")
        if item.status != "QUEUED":
            raise TikTokError(f"{item.item_id} is {item.status}; it can be posted only once")
        video = self.path(item)
        if _sha256(video) != item.checks.get("video_sha256"):
            raise TikTokError("video changed since it was checked - re-queue it")
        if not item.checks.get("ok"):
            raise TikTokError("checks did not pass: " + "; ".join(item.checks["problems"]))
        post_info = None
        if not draft:
            if privacy not in creator.get("privacy_level_options", []):
                raise TikTokError("choose one of the privacy options TikTok offers this account")
            if options.get("brand_content_toggle") and privacy == "SELF_ONLY":
                raise TikTokError("branded content cannot be private")
            post_info = {"title": item.caption, "privacy_level": privacy,
                         "disable_comment": bool(options.get("disable_comment")
                                                 or creator.get("comment_disabled")),
                         "disable_duet": bool(options.get("disable_duet")
                                              or creator.get("duet_disabled")),
                         "disable_stitch": bool(options.get("disable_stitch")
                                                or creator.get("stitch_disabled")),
                         "brand_content_toggle": bool(options.get("brand_content_toggle")),
                         "brand_organic_toggle": bool(options.get("brand_organic_toggle")),
                         "is_aigc": item.is_aigc}
        self.audit.append("approval.granted", approver, {
            "capability": "publish.tiktok", "request_id": item.item_id,
            "bound_sha256": item.checks["video_sha256"],
            "privacy": privacy or "inbox_draft", "is_aigc": item.is_aigc})
        try:
            init = client.init_upload(video.stat().st_size, post_info)
            item.publish_id = init["publish_id"]
            client.upload(init["upload_url"], video)
            st: dict[str, Any] = {}
            for _ in range(poll):
                st = client.status(item.publish_id)
                if st.get("status") in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX", "FAILED"):
                    break
                time.sleep(5)
        except TikTokError as e:
            item.status = "FAILED"
            item.result = {"error": str(e)[:300]}
            self.save(item)
            self.audit.append("tiktok.failed", approver, {"item_id": item.item_id})
            raise
        item.result = {k: st.get(k) for k in ("status", "fail_reason",
                                              "publicaly_available_post_id")}
        if st.get("status") == "FAILED":
            item.status = "FAILED"
        elif draft:
            item.status = "DRAFTED"
        else:
            item.status = "POSTED"
        self.save(item)
        self.audit.append("tiktok.published", approver, {
            "item_id": item.item_id, "status": item.status,
            "tiktok_status": st.get("status") or "PROCESSING",
            "account": ref(creator.get("creator_username", ""))})
        return item


# ------------------------------------------------------------------ the review screen

def _choose(ask: Any, prompt: str, valid: dict[str, Any]) -> Any:
    while True:
        ans = (ask(prompt) or "").strip().lower()
        if ans in valid:
            return valid[ans]


def review(queue: TikTokQueue, client: TikTokClient, approver: str, ask: Any = input,
           say: Any = print, draft: bool = False, preview: Any = None) -> list[QueueItem]:
    """One pass over the queue. For each video the owner sees what TikTok requires and
    answers y (post now), s (skip for later) or r (reject). 'y' uploads immediately."""
    if not approver.startswith("human:"):
        raise PermissionError("the review must be done by a human at a terminal")
    pending = queue.pending()
    if not pending:
        say("Nothing waiting for review.")
        return []
    creator = client.creator_info()
    acct = f"{creator.get('creator_nickname', '?')} (@{creator.get('creator_username', '?')})"
    max_s = creator.get("max_video_post_duration_sec")
    done = []
    for n, item in enumerate(pending, 1):
        video = queue.path(item)
        say(f"\n[{n}/{len(pending)}] {item.item_id}  ->  TikTok account: {acct}")
        say(f"  video:   {video}")
        secs = duration_sec(video)
        if secs is not None:
            say(f"  length:  {secs:.1f}s" + (f" (account max {max_s}s)" if max_s else ""))
        say(f"  caption: {item.caption}")
        say(f"  AI-generated label: {'ON' if item.is_aigc else 'off'}"
            f"    compliance gate: {item.checks.get('gate')}")
        problems = list(item.checks.get("problems", []))
        if secs is not None and max_s and secs > float(max_s):
            problems.append(f"video is longer than this account allows ({max_s}s)")
        if problems:
            for p in problems:
                say(f"  BLOCKED: {p}")
            act = _choose(ask, "  [s]kip / [r]eject: ", {"s": "skip", "r": "reject"})
            if act == "reject":
                item.status = "REJECTED"
                queue.save(item)
            continue
        if preview is not None and _choose(ask, "  Preview first? [y/n]: ",
                                           {"y": True, "n": False}):
            preview(video)
        privacy, options = None, {}
        if not draft:
            opts = list(creator.get("privacy_level_options") or [])
            for i, o in enumerate(opts, 1):
                say(f"    {i}. {PRIVACY_LABELS.get(o, o)}")
            privacy = _choose(ask, "  Who can view this video? (number, no default): ",
                              {str(i): o for i, o in enumerate(opts, 1)})
            kind = _choose(ask, "  Does it promote something? [n]o / [y]our own brand / "
                                "[b]randed content for someone else: ",
                           {"n": None, "": None, "y": "own", "b": "branded"})
            options = {"brand_organic_toggle": kind == "own",
                       "brand_content_toggle": kind == "branded"}
            if kind == "branded" and privacy == "SELF_ONLY":
                say("  Branded content can't be 'Only me' - choose again.")
                privacy = _choose(ask, "  Who can view this video? (number): ",
                                  {str(i): o for i, o in enumerate(opts, 1)
                                   if o != "SELF_ONLY"})
            say("  " + (BRANDED_CONFIRMATION if kind == "branded" else MUSIC_CONFIRMATION))
            say("  It can take a few minutes for TikTok to process the video after posting.")
        verb = "Send to TikTok drafts" if draft else "Post now"
        act = _choose(ask, f"  {verb}? [y]es / [s]kip / [r]eject: ",
                      {"y": "post", "s": "skip", "r": "reject"})
        if act == "skip":
            continue
        if act == "reject":
            item.status = "REJECTED"
            queue.save(item)
            continue
        try:
            item = queue.post(item, client, approver, privacy, options, creator, draft=draft)
            say(f"  -> {item.status} ({item.result.get('status') or 'processing'})")
        except TikTokError as e:
            say(f"  -> FAILED: {e}")
        done.append(item)
    return done
