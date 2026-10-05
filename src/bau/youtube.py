"""YouTube: review-and-upload (YouTube Data API v3), with made-for-kids built in.

Same shape as ``tiktok.py``: the machine prepares the video, title, description,
provenance and compliance checks and queues it; the owner reviews each video and only
their confirmation uploads it. Nothing posts on its own.

For every video the owner must choose the audience (made for kids or not, no default:
the creator is legally responsible for it under COPPA) and who can see it. A video queued
as made for kids has run the kids rules (``bau.kids`` + ``kids_content.yaml``), cannot be
switched to "not for kids" at review, and needs the owner to confirm they watched it all.

API facts verified 2026-10-05 against developers.google.com/youtube/v3:
  OAuth   https://accounts.google.com/o/oauth2/v2/auth (installed app: loopback redirect on
          127.0.0.1, PKCE S256), token https://oauth2.googleapis.com/token
  Scopes  youtube.upload (insert), youtube.readonly (which channel is connected)
  Upload  POST https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable
          &part=snippet,status -> Location session URI; PUT chunks (multiples of 256 KiB,
          Content-Range); 308 = keep going (Range header), 200/201 = done with the video.
  Fields  status.privacyStatus public|unlisted|private, status.selfDeclaredMadeForKids,
          status.containsSyntheticMedia; title <= 100 chars, description <= 5000 bytes,
          tags <= 500 chars, no < or > in title/description.
  Quota   videos.insert: 1 unit of the Video Uploads bucket (100 per day).
  Unverified API projects (created after 2020-07-28): uploads are private until the
  project passes Google's audit.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import http.server
import json
import os
import secrets
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .audit import AuditLog, ref
from .home import atomic_write_json, bau_home
from .store import JsonlStore, YamlStore
from .tiktok import _env_file, _sha256, duration_sec

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"
SCOPES = ("https://www.googleapis.com/auth/youtube.upload "
          "https://www.googleapis.com/auth/youtube.readonly")
VIDEO_TYPES = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
               ".mkv": "video/x-matroska", ".avi": "video/x-msvideo"}
CHUNK = 32 * 256 * 1024                  # 8 MiB, a multiple of 256 KiB
PRIVACY_LABELS = {"public": "Public", "unlisted": "Unlisted (link only)",
                  "private": "Private (only you)"}
CATEGORIES = {"1": "Film & Animation", "10": "Music", "22": "People & Blogs",
              "24": "Entertainment", "27": "Education"}
DEFAULTS = {"max_uploads_per_day": 3, "category_id": "1", "language": "en",
            "notify_subscribers": True}


class YouTubeError(RuntimeError):
    pass


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge.rstrip(b"=").decode()     # RFC 7636 S256


def app_credentials(env_file: Path = Path("/etc/bau/platforms.env")) -> tuple[str, str]:
    env = {**_env_file(env_file), **os.environ}
    cid, secret = env.get("YOUTUBE_CLIENT_ID"), env.get("YOUTUBE_CLIENT_SECRET")
    if not cid or not secret:
        raise YouTubeError("set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET "
                           "(on the laptop: /etc/bau/platforms.env)")
    return cid, secret


class TokenStore:
    """Tokens live in BAU_HOME/secrets/youtube.json, mode 0600. Never logged."""

    def __init__(self, home: Path | None = None):
        self.path = (home or bau_home()) / "secrets" / "youtube.json"

    def load(self) -> dict[str, Any] | None:
        return json.loads(self.path.read_text()) if self.path.exists() else None

    def save(self, tok: dict[str, Any]) -> None:
        old = self.load() or {}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, stat.S_IRWXU)
        # Google sends a refresh token on the first consent only; keep the one we have.
        rec = {"access_token": tok["access_token"],
               "refresh_token": tok.get("refresh_token") or old.get("refresh_token", ""),
               "scope": tok.get("scope", old.get("scope", "")),
               "access_expires_at": time.time() + int(tok.get("expires_in", 0)) - 60}
        atomic_write_json(self.path, rec)
        os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


class Http:
    """Transport that also returns response headers (resumable uploads need them)."""

    def request(self, method: str, url: str, headers: dict[str, str],
                body: bytes | None = None, timeout: int = 120
                ) -> tuple[int, dict[str, str], bytes]:
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
        except urllib.error.HTTPError as e:
            return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read()


class YouTubeClient:
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
        q = {"client_id": self.creds[0], "redirect_uri": redirect_uri, "response_type": "code",
             "scope": SCOPES, "state": state, "code_challenge": challenge,
             "code_challenge_method": "S256", "access_type": "offline", "prompt": "consent"}
        return AUTH_URL + "?" + urllib.parse.urlencode(q)

    def _token(self, form: dict[str, str]) -> dict[str, Any]:
        cid, secret = self.creds
        body = urllib.parse.urlencode({"client_id": cid, "client_secret": secret,
                                       **form}).encode()
        code, _, raw = self.http.request("POST", TOKEN_URL, {
            "Content-Type": "application/x-www-form-urlencoded"}, body)
        data = json.loads(raw or b"{}")
        if code != 200 or "access_token" not in data:
            raise YouTubeError("token request failed: "
                               f"{data.get('error_description') or data.get('error') or code}")
        self.tokens.save(data)
        return data

    def exchange(self, code: str, redirect_uri: str, verifier: str) -> dict[str, Any]:
        return self._token({"code": code, "grant_type": "authorization_code",
                            "redirect_uri": redirect_uri, "code_verifier": verifier})

    def access_token(self) -> str:
        tok = self.tokens.load()
        if tok is None:
            raise YouTubeError("not connected: run `bau youtube login`")
        if time.time() < tok["access_expires_at"]:
            return tok["access_token"]
        if not tok.get("refresh_token"):
            raise YouTubeError("YouTube login expired: run `bau youtube login` again")
        return self._token({"grant_type": "refresh_token",
                            "refresh_token": tok["refresh_token"]})["access_token"]

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        code, _, raw = self.http.request("GET", f"{API}{path}?{urllib.parse.urlencode(params)}",
                                         {"Authorization": f"Bearer {self.access_token()}"})
        data = json.loads(raw or b"{}")
        if code != 200:
            raise YouTubeError(f"{path}: {(data.get('error') or {}).get('message') or code}")
        return data

    # -------------------------------------------------------- Data API
    def channel(self) -> dict[str, Any]:
        items = self._get("/channels", {"part": "snippet", "mine": "true"}).get("items") or []
        if not items:
            raise YouTubeError("this Google account has no YouTube channel")
        return {"id": items[0]["id"], "title": items[0]["snippet"].get("title", "?"),
                "handle": items[0]["snippet"].get("customUrl", "")}

    def upload(self, video: Path, resource: dict[str, Any], notify: bool = True
               ) -> dict[str, Any]:
        size = video.stat().st_size
        ctype = VIDEO_TYPES.get(video.suffix.lower(), "application/octet-stream")
        meta = json.dumps(resource).encode()
        q = urllib.parse.urlencode({"uploadType": "resumable", "part": "snippet,status",
                                    "notifySubscribers": str(notify).lower()})
        code, hdr, raw = self.http.request("POST", f"{UPLOAD}?{q}", {
            "Authorization": f"Bearer {self.access_token()}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(size), "X-Upload-Content-Type": ctype}, meta)
        session = hdr.get("location")
        if code != 200 or not session:
            err = (json.loads(raw or b"{}").get("error") or {}).get("message") or code
            raise YouTubeError(f"upload refused: {err}")
        start, fails = 0, 0
        with video.open("rb") as fh:
            while True:
                fh.seek(start)
                body = fh.read(CHUNK)
                end = start + len(body) - 1
                code, hdr, raw = self.http.request("PUT", session, {
                    "Authorization": f"Bearer {self.access_token()}",
                    "Content-Length": str(len(body)), "Content-Type": ctype,
                    "Content-Range": f"bytes {start}-{end}/{size}"}, body, 600)
                if code in (200, 201):
                    return json.loads(raw or b"{}")
                if code == 308:             # keep going from what YouTube has
                    rng = hdr.get("range", "")
                    start = int(rng.rsplit("-", 1)[1]) + 1 if rng else 0
                    fails = 0
                    continue
                if code >= 500 and fails < 4:
                    fails += 1
                    time.sleep(2 ** fails)
                    probe, hdr, _ = self.http.request("PUT", session, {
                        "Authorization": f"Bearer {self.access_token()}",
                        "Content-Length": "0", "Content-Range": f"bytes */{size}"}, b"")
                    rng = hdr.get("range", "") if probe == 308 else ""
                    start = int(rng.rsplit("-", 1)[1]) + 1 if rng else 0
                    continue
                err = (json.loads(raw or b"{}").get("error") or {}).get("message") or code
                raise YouTubeError(f"upload failed at byte {start}: {err}")

    def status(self, video_id: str) -> dict[str, Any]:
        items = self._get("/videos", {"part": "status,processingDetails",
                                      "id": video_id}).get("items") or []
        if not items:
            return {"uploadStatus": "unknown"}
        st = items[0].get("status", {})
        return {"uploadStatus": st.get("uploadStatus"), "privacyStatus": st.get("privacyStatus"),
                "madeForKids": st.get("madeForKids"),
                "rejectionReason": st.get("rejectionReason") or st.get("failureReason"),
                "processing": (items[0].get("processingDetails") or {}).get("processingStatus")}


def login(client: YouTubeClient, port: int = 3456, open_browser: Any = None,
          timeout: int = 300) -> dict[str, Any]:
    """Installed-app OAuth with a one-shot callback server on 127.0.0.1 (Google allows
    any loopback port for Desktop app clients)."""
    redirect = f"http://127.0.0.1:{port}/"
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(24)
    got: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            got.update(dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query)))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"BAU: YouTube connected. You can close this tab.")

        def log_message(self, *a: Any) -> None:
            pass

    srv = http.server.HTTPServer(("127.0.0.1", port), Handler)
    srv.timeout = timeout
    url = client.authorize_url(redirect, state, challenge)
    (open_browser or (lambda u: print(f"Open this link to connect YouTube:\n{u}")))(url)
    srv.handle_request()
    srv.server_close()
    if not got:
        raise YouTubeError("no answer from Google (timed out)")
    if not secrets.compare_digest(got.get("state", ""), state):
        raise YouTubeError("state mismatch - login aborted")
    if "code" not in got:
        raise YouTubeError(f"Google refused: {got.get('error')}")
    return client.exchange(got["code"], redirect, verifier)


# ------------------------------------------------------------------ queue

@dataclass
class QueueItem:
    item_id: str
    video: str                           # path relative to BAU_HOME/artifacts
    title: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    kids: bool = False                   # queued as made for kids: kids rules ran
    licensed: bool = False               # owner holds a licence for third-party characters
    paid_promotion: bool = False
    category_id: str = "1"
    is_aigc: bool = True
    created_at: str = ""
    created_by: str = ""
    status: str = "QUEUED"               # QUEUED | POSTED | REJECTED | FAILED
    checks: dict[str, Any] = field(default_factory=dict)
    video_id: str = ""
    result: dict[str, Any] = field(default_factory=dict)


class YouTubeQueue:
    def __init__(self, home: Path | None = None, audit: AuditLog | None = None):
        self.home = home or bau_home()
        self.store = JsonlStore(self.home / "publish" / "youtube" / "queue.jsonl")
        self.audit = audit or AuditLog(self.home / "audit" / "chain.jsonl")
        self.cfg = {**DEFAULTS, **(YamlStore(self.home / "config" / "youtube.yaml").load()
                                   or {})}

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

    def add(self, video: Path, title: str, by: str, description: str = "",
            tags: list[str] | None = None, kids: bool = False, licensed: bool = False,
            paid_promotion: bool = False, category_id: str | None = None,
            is_aigc: bool | None = None, engine: Any = None) -> QueueItem:
        arts = (self.home / "artifacts").resolve()
        video = video.resolve()
        if not video.is_file() or not video.is_relative_to(arts):
            raise YouTubeError("video must be a file inside BAU_HOME/artifacts")
        if video.suffix.lower() not in VIDEO_TYPES:
            raise YouTubeError(f"YouTube upload accepts {', '.join(sorted(VIDEO_TYPES))}")
        tags = [t.strip() for t in (tags or []) if t.strip()]
        if not title.strip() or len(title) > 100:
            raise YouTubeError("title must be 1-100 characters")
        if len(description.encode()) > 5000:
            raise YouTubeError("description longer than YouTube's 5000 bytes")
        if any(c in title + description for c in "<>"):
            raise YouTubeError("YouTube does not allow < or > in the title or description")
        if sum(len(t) + (2 if " " in t else 0) for t in tags) + max(0, len(tags) - 1) > 500:
            raise YouTubeError("tags longer than YouTube's 500 characters")
        item = QueueItem(item_id="yt_" + secrets.token_hex(5), video=str(video.relative_to(arts)),
                         title=title.strip(), description=description, tags=tags, kids=kids,
                         licensed=licensed, paid_promotion=paid_promotion,
                         category_id=category_id or str(self.cfg["category_id"]),
                         created_at=dt.datetime.now(dt.UTC).isoformat(), created_by=by)
        item.checks = self.check(item, is_aigc, engine)
        item.is_aigc = item.checks["is_aigc"]
        self.save(item)
        self.audit.append("youtube.queued", by, {"item_id": item.item_id, "kids": kids,
                                                 "gate": item.checks["gate"]})
        return item

    def check(self, item: QueueItem, is_aigc: bool | None = None, engine: Any = None
              ) -> dict[str, Any]:
        """Everything decidable before the owner looks. Problems block; warnings show."""
        from . import kids as kidsmod
        from .claims import scan
        from .disclosure import Provenance, check_publication
        from .platforms import PlatformRegistry
        video = self.path(item)
        problems: list[str] = []
        warnings: list[str] = []
        prov_path = video.with_suffix(video.suffix + ".provenance.json")
        prov = None
        if prov_path.exists():
            raw = json.loads(prov_path.read_text())
            if raw.get("artifact_sha256") and raw["artifact_sha256"] != _sha256(video):
                problems.append("video changed after its provenance record was written")
            prov = Provenance(**{k: v for k, v in raw.items()
                                 if k in Provenance.__dataclass_fields__})
        ai = bool(prov.ai_generated or prov.synthetic_media) if prov else is_aigc is not False
        if is_aigc is False and ai:
            problems.append("provenance says AI-generated: the AI label cannot be turned off")
        is_aigc = True if ai else bool(is_aigc)
        text = f"{item.title}\n{item.description}"
        claims = scan(text)
        if claims:
            problems.append("title or description makes claims that need evidence: "
                            + ", ".join(sorted({c["claim_type"] for c in claims})))
        plat = PlatformRegistry(self.home).facts("youtube")
        if not plat["platform_policy_current"]:
            why = plat.get("reason") or f"{plat.get('policy_age_days')} days old"
            problems.append(f"YouTube policy record missing or stale ({why}): "
                            "bau platform add examples/platform-youtube.yaml")
        ctx: dict[str, Any] = {"audience": [{"country": "US"}], "platform_requires_ai_label": True,
                               "platform_label_set": is_aigc,
                               "human_editorial_responsibility": True,
                               "paid_promotion": item.paid_promotion}
        issues: list[dict[str, str]] = []
        dup = None
        if item.kids:
            issues = kidsmod.scan(item.title, item.description, item.tags)
            dup = kidsmod.near_duplicate(item.title, [(i.item_id, i.title) for i in self.items()
                                                      if i.kids and i.item_id != item.item_id
                                                      and i.status != "REJECTED"])
            ctx.update(kidsmod.facts(issues, licensed=item.licensed,
                                     paid_promotion=item.paid_promotion,
                                     near_duplicate=dup is not None))
        gate = "UNKNOWN"
        if engine is not None:
            p = prov or (Provenance(item.item_id, "video", True, False, False, True,
                                    visible_disclosure_text="AI-GENERATED VIDEO") if ai
                         else Provenance(item.item_id, "video", False, False, True, False))
            d = check_publication(p, ctx, engine)
            gate = str(d.status)
            for f in d.to_dict()["findings"]:
                if f["status"] not in ("PASS", "PASS_WITH_REVIEW", "NOT_APPLICABLE"):
                    problems.append(f["message"])
                elif f["status"] == "PASS_WITH_REVIEW" and (f.get("detail") or {}).get("failed"):
                    warnings.append(f["message"])
        # Spell out exactly what tripped the kids rules (the rules only see true/false).
        problems += [i["detail"] for i in issues
                     if i["issue"] != "franchise" or not item.licensed]
        if dup:
            warnings.append(f"title is almost the same as {dup}: give each episode its own "
                            "story so YouTube does not treat the channel as mass-produced")
        return {"gate": gate, "is_aigc": is_aigc, "provenance": bool(prov),
                "kids_issues": issues, "problems": list(dict.fromkeys(problems)),
                "warnings": warnings, "ok": not problems and gate != "UNKNOWN",
                "video_sha256": _sha256(video),
                "checked_at": dt.datetime.now(dt.UTC).isoformat()}

    def posted_last_24h(self) -> int:
        since = dt.datetime.now(dt.UTC) - dt.timedelta(hours=24)
        return sum(1 for i in self.items() if i.status == "POSTED"
                   and dt.datetime.fromisoformat(i.result.get("at", "1970-01-01T00:00:00+00:00"))
                   >= since)

    # -------------------------------------------------------- the owner's click
    def post(self, item: QueueItem, client: YouTubeClient, approver: str, privacy: str,
             made_for_kids: bool, watched: bool = False, channel: dict[str, Any] | None = None
             ) -> QueueItem:
        """Called only after the owner chose the audience and privacy and confirmed."""
        if not approver.startswith("human:"):
            raise PermissionError("only a human at the review screen can upload to YouTube")
        if item.status != "QUEUED":
            raise YouTubeError(f"{item.item_id} is {item.status}; it can be uploaded only once")
        if privacy not in PRIVACY_LABELS:
            raise YouTubeError("choose who can see it: public, unlisted or private")
        if item.kids and not made_for_kids:
            raise YouTubeError("this video was queued as made for kids and must stay that way")
        if made_for_kids and not item.kids:
            raise YouTubeError("made for kids, but the kids checks never ran: "
                               "re-queue it with --kids")
        if item.kids and not watched:
            raise YouTubeError("watch the whole video before a made-for-kids upload")
        video = self.path(item)
        if _sha256(video) != item.checks.get("video_sha256"):
            raise YouTubeError("video changed since it was checked - re-queue it")
        if not item.checks.get("ok"):
            raise YouTubeError("checks did not pass: " + "; ".join(item.checks["problems"]))
        cap = int(self.cfg["max_uploads_per_day"])
        if self.posted_last_24h() >= cap:
            raise YouTubeError(f"daily limit reached ({cap} uploads in 24h; change it in "
                               "config/youtube.yaml). Steady channels beat bursts.")
        if item.paid_promotion and privacy != "private":
            raise YouTubeError("paid promotion: upload as private, tick 'includes paid "
                               "promotion' in YouTube Studio, then make it public there")
        resource = {"snippet": {"title": item.title, "description": item.description,
                                "tags": item.tags, "categoryId": item.category_id,
                                "defaultLanguage": self.cfg["language"]},
                    "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": made_for_kids,
                               "containsSyntheticMedia": item.is_aigc, "embeddable": True,
                               "license": "youtube"}}
        self.audit.append("approval.granted", approver, {
            "capability": "publish.youtube", "request_id": item.item_id,
            "bound_sha256": item.checks["video_sha256"], "privacy": privacy,
            "made_for_kids": made_for_kids, "is_aigc": item.is_aigc})
        try:
            out = client.upload(video, resource, notify=bool(self.cfg["notify_subscribers"]))
        except YouTubeError as e:
            item.status = "FAILED"
            item.result = {"error": str(e)[:300]}
            self.save(item)
            self.audit.append("youtube.failed", approver, {"item_id": item.item_id})
            raise
        item.video_id = out.get("id", "")
        st = out.get("status") or {}
        item.status = "POSTED"
        item.result = {"at": dt.datetime.now(dt.UTC).isoformat(),
                       "url": f"https://youtu.be/{item.video_id}" if item.video_id else "",
                       "uploadStatus": st.get("uploadStatus"),
                       "privacyStatus": st.get("privacyStatus") or privacy,
                       "requested_privacy": privacy}
        if privacy != "private" and st.get("privacyStatus") == "private":
            item.result["note"] = ("YouTube kept it private: the API project is not audited "
                                   "yet. Make it public in YouTube Studio, or finish the audit.")
        self.save(item)
        self.audit.append("youtube.published", approver, {
            "item_id": item.item_id, "video_id": item.video_id,
            "made_for_kids": made_for_kids,
            "channel": ref((channel or {}).get("id", ""))})
        return item


# ------------------------------------------------------------------ the review screen

def _choose(ask: Any, prompt: str, valid: dict[str, Any]) -> Any:
    while True:
        ans = (ask(prompt) or "").strip().lower()
        if ans in valid:
            return valid[ans]


def review(queue: YouTubeQueue, client: YouTubeClient, approver: str, ask: Any = input,
           say: Any = print, preview: Any = None) -> list[QueueItem]:
    """One pass over the queue: for each video the owner sees the channel, the video and
    every setting, chooses the audience and privacy (no defaults) and confirms."""
    if not approver.startswith("human:"):
        raise PermissionError("the review must be done by a human at a terminal")
    pending = queue.pending()
    if not pending:
        say("Nothing waiting for review.")
        return []
    ch = client.channel()
    done = []
    for n, item in enumerate(pending, 1):
        video = queue.path(item)
        say(f"\n[{n}/{len(pending)}] {item.item_id}  ->  YouTube channel: {ch['title']} "
            f"{ch.get('handle', '')}".rstrip())
        say(f"  video:       {video}")
        secs = duration_sec(video)
        if secs is not None:
            say(f"  length:      {secs:.1f}s")
        say(f"  title:       {item.title}")
        if item.description:
            say("  description: " + item.description.splitlines()[0][:100]
                + (" ..." if len(item.description) > 100 or "\n" in item.description else ""))
        if item.tags:
            say(f"  tags:        {', '.join(item.tags)}")
        say(f"  category:    {CATEGORIES.get(item.category_id, item.category_id)}")
        say(f"  AI label:    {'ON' if item.is_aigc else 'off'}    compliance gate: "
            f"{item.checks.get('gate')}")
        if item.kids:
            say("  audience:    MADE FOR KIDS (comments, personalised ads, notifications and "
                "end screens will be off)")
        for w in item.checks.get("warnings", []):
            say(f"  NOTE: {w}")
        problems = list(item.checks.get("problems", []))
        if problems:
            for p in problems:
                say(f"  BLOCKED: {p}")
            if _choose(ask, "  [s]kip / [r]eject: ", {"s": "skip", "r": "reject"}) == "reject":
                item.status = "REJECTED"
                queue.save(item)
            continue
        watched = False
        if item.kids:
            if preview is not None:
                preview(video)
            watched = _choose(ask, "  Did you watch the whole video? [y/n]: ",
                              {"y": True, "n": False})
            if not watched:
                say("  Watch it first - kids videos go out only after a full watch.")
                continue
            mfk = True
        else:
            if preview is not None and _choose(ask, "  Preview first? [y/n]: ",
                                               {"y": True, "n": False}):
                preview(video)
            mfk = _choose(ask, "  Is this video made for kids? (y/n, no default - you are "
                               "legally responsible for this answer): ",
                          {"y": True, "n": False})
            if mfk:
                say("  Then it needs the kids checks first: re-queue it with --kids.")
                continue
        opts = list(PRIVACY_LABELS)
        for i, o in enumerate(opts, 1):
            say(f"    {i}. {PRIVACY_LABELS[o]}")
        privacy = _choose(ask, "  Who can see it? (number, no default): ",
                          {str(i): o for i, o in enumerate(opts, 1)})
        if item.paid_promotion and privacy != "private":
            say("  Paid promotion: uploading as private; tick 'includes paid promotion' in "
                "YouTube Studio before making it public.")
            privacy = "private"
        act = _choose(ask, "  Upload now? [y]es / [s]kip / [r]eject: ",
                      {"y": "post", "s": "skip", "r": "reject"})
        if act == "skip":
            continue
        if act == "reject":
            item.status = "REJECTED"
            queue.save(item)
            continue
        try:
            item = queue.post(item, client, approver, privacy, mfk, watched, ch)
            say(f"  -> POSTED {item.result.get('url', '')} ({item.result.get('privacyStatus')})")
            if item.result.get("note"):
                say(f"     {item.result['note']}")
        except YouTubeError as e:
            say(f"  -> FAILED: {e}")
        done.append(item)
    return done
