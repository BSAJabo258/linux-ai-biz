"""A week of the creator's posts: the owner approves it once, Ayrshare posts it on schedule.

The owner's choice (2026-11-01): batch approval instead of a click per post. A week plan
(``BAU_HOME/weeks/NAME.yaml``) lists each post: when, platform, tier, caption, media file.
Jarvis can only put it on the owner's screen as ONE card that shows every post; the owner
picks TikTok's visibility there (no default) and one confirm schedules them all. Any change
to the plan or a media file after the card voids it. Each week is sent once.

Rules checked on every post: Instagram and TikTok only (sfw), the platform's AI label on,
an AI disclosure in the caption, nothing that refers to minors
(``virtual_creator.MINOR_REFERENCE``), a time zone and a time in the future, media inside
``BAU_HOME/artifacts/media`` and at most 30 MB. Fanvue (explicit) is not an Ayrshare network:
its own adapter is planned.

API facts verified 2026-11-01 against https://www.ayrshare.com/docs (apis/post/post.md,
apis/post/social-networks/instagram.md and tiktok.md, apis/media/upload-media.md):
  POST https://api.ayrshare.com/api/post, header Authorization: Bearer API_KEY
    body: post (text), platforms (instagram, tiktok, ...), mediaUrls (https only),
    scheduleDate (UTC, YYYY-MM-DDThh:mm:ssZ), validateScheduled (default true: checked when
    scheduled), idempotencyKey (a repeat is rejected). Videos need a paid Ayrshare plan.
  instagramOptions.isAIGenerated: Instagram's "AI info" label; cannot be changed later.
  tikTokOptions.isAIGenerated: "Creator labeled as AI-generated"; cannot be changed later.
  tikTokOptions.visibility: public | private | followers (private accounts) | friends.
  POST https://api.ayrshare.com/api/media/upload: file as a base64 data URI, max 30 MB;
    returns {"url": ...}; stored 90 days.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import mimetypes
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from .audit import AuditLog
from .virtual_creator import MINOR_REFERENCE

API = "https://api.ayrshare.com/api"
PLATFORMS = ("instagram", "tiktok")
VISIBILITY = ("public", "private", "followers", "friends")
MAX_MEDIA = 30 * 1024 * 1024
DISCLOSURE = re.compile(r"(#ai\b|\bai[- ](generated|creator|model|influencer|art)\b|"
                        r"\bvirtual (creator|influencer|model)\b|\bmade with ai\b)", re.I)
NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,60}$")
PICTURES = (".png", ".jpg", ".jpeg", ".webp")   # videos: no age check yet


class WeekError(ValueError):
    pass


def _dir(home: Path) -> Path:
    return home / "weeks"


def _load(home: Path, name: str) -> list[dict[str, Any]]:
    if not NAME.match(name or ""):
        raise WeekError("a week name is lowercase letters, digits, dot, dash")
    path = _dir(home) / f"{name}.yaml"
    if not path.is_file():
        have = sorted(p.stem for p in _dir(home).glob("*.yaml"))
        raise WeekError(f"no week plan {name!r}; the plans are: {', '.join(have) or 'none'}")
    posts = (yaml.safe_load(path.read_text()) or {}).get("posts") or []
    if not isinstance(posts, list) or not posts:
        raise WeekError(f"{path.name}: no posts")
    return posts


def _media(home: Path, name: str) -> Path | None:
    root = (home / "artifacts" / "media").resolve()
    p = (root / str(name)).resolve()
    return p if p.is_relative_to(root) and p.is_file() else None


def _when(value: Any) -> dt.datetime | None:
    try:
        t = value if isinstance(value, dt.datetime) else dt.datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return t


def problems(home: Path, name: str, now: dt.datetime | None = None) -> list[str]:
    now = now or dt.datetime.now(dt.UTC)
    out = []
    for i, p in enumerate(_load(home, name), 1):
        say = f"post {i}"
        if p.get("platform") == "fanvue":
            out.append(f"{say}: Fanvue is not an Ayrshare network; its adapter is planned")
        elif p.get("platform") not in PLATFORMS:
            out.append(f"{say}: platform must be one of {', '.join(PLATFORMS)}")
        if p.get("tier", "sfw") != "sfw":
            out.append(f"{say}: Instagram and TikTok get sfw only")
        caption = str(p.get("caption") or "")
        if m := MINOR_REFERENCE.search(caption):
            out.append(f"{say}: refers to minors ({m.group(0)!r}); BAU never posts that")
        if not DISCLOSURE.search(caption):
            out.append(f"{say}: the caption needs an AI disclosure (e.g. #AI, AI-generated)")
        t = _when(p.get("when"))
        if t is None:
            out.append(f"{say}: 'when' is not a date and time")
        elif t.tzinfo is None:
            out.append(f"{say}: 'when' needs a time zone (e.g. -05:00 for Michigan)")
        elif t <= now:
            out.append(f"{say}: 'when' is in the past")
        m = _media(home, p.get("media", ""))
        if m is None:
            out.append(f"{say}: media must be a file in BAU_HOME/artifacts/media")
        elif m.stat().st_size > MAX_MEDIA:
            out.append(f"{say}: media is over Ayrshare's 30 MB upload limit")
        elif m.suffix.lower() in PICTURES and not _age_checked(m):
            out.append(f"{say}: {m.name} has no passed age check on record; draw it with "
                       "bau creator draw, which checks every picture")
    return out


def _age_checked(picture: Path) -> bool:
    """Nothing childlike: a picture is used only with a passed age check on record."""
    try:
        prov = json.loads(picture.with_name(picture.name + ".provenance.json").read_text())
    except (OSError, ValueError):
        return False
    return (prov.get("age_check") or {}).get("passed") is True


def digest(home: Path, name: str) -> str:
    """The plan and every media file: any change gives a different digest."""
    h = hashlib.sha256()
    posts = _load(home, name)
    h.update(json.dumps(posts, sort_keys=True, default=str).encode())
    for p in posts:
        m = _media(home, p.get("media", ""))
        h.update(m.read_bytes() if m else b"missing")
    return h.hexdigest()


def stage(home: Path, name: str) -> dict[str, Any]:
    """The one card the owner sees: every post, and TikTok's visibility to choose."""
    found = problems(home, name)
    if found:
        raise WeekError("; ".join(found))
    posts = _load(home, name)
    _dir(home).joinpath(f"{name}.staged").write_text(digest(home, name))
    lines = [f"{_when(p['when']):%a %b %d %H:%M %Z} {p['platform']}: "
             f"{str(p['caption'])[:70]} [{p['media']}]" for p in posts]
    card: dict[str, Any] = {"summary": f"Schedule {len(posts)} posts ({name}) with the AI "
                                       "label on each:\n" + "\n".join(lines)}
    if any(p["platform"] == "tiktok" for p in posts):
        card["form"] = {"fields": [{"name": "tiktok_visibility",
                                    "label": "Who can see the TikTok posts",
                                    "options": [[v, v] for v in VISIBILITY]}]}
    return card


def send(home: Path, name: str, tiktok_visibility: str, api: Any, by: str) -> dict[str, Any]:
    if not by.startswith("human:"):
        raise PermissionError("only the owner sends a week")
    sent = _dir(home) / f"{name}.sent.json"
    if sent.exists():
        raise WeekError(f"{name} was already scheduled ({sent.name})")
    staged = _dir(home) / f"{name}.staged"
    if not staged.exists() or staged.read_text().strip() != digest(home, name):
        raise WeekError(f"{name} changed after it was shown to the owner: show it again")
    found = problems(home, name)
    if found:
        raise WeekError("; ".join(found))
    posts = _load(home, name)
    if any(p["platform"] == "tiktok" for p in posts) and tiktok_visibility not in VISIBILITY:
        raise WeekError("the owner picks the TikTok visibility: " + ", ".join(VISIBILITY))
    key = digest(home, name)[:16]
    results = []
    for i, p in enumerate(posts):
        body: dict[str, Any] = {
            "post": str(p["caption"]), "platforms": [p["platform"]],
            "mediaUrls": [api.upload(_media(home, p["media"]))],
            "scheduleDate": _when(p["when"]).astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "idempotencyKey": f"bau-{key}-{i}"}
        if p["platform"] == "instagram":
            body["instagramOptions"] = {"isAIGenerated": True}
        else:
            body["tikTokOptions"] = {"isAIGenerated": True, "visibility": tiktok_visibility}
        results.append({"when": body["scheduleDate"], "platform": p["platform"],
                        "answer": api.post(body)})
    sent.write_text(json.dumps(results, indent=1, default=str))
    AuditLog(home / "audit" / "chain.jsonl").append(
        "week.scheduled", by, {"week": name, "posts": len(results), "digest": key})
    return {"scheduled": len(results), "week": name, "results": results}


class Ayrshare:
    """The real client (stdlib only). The key stays here: never in a prompt or a log."""

    def __init__(self, api_key: str, opener: Any = None):
        self.key = api_key
        self.open = opener or urllib.request.urlopen

    def _call(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(API + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {self.key}",
                                              "Content-Type": "application/json"})
        with self.open(req, timeout=120) as r:
            return json.loads(r.read() or b"{}")

    def upload(self, path: Path) -> str:
        kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = f"data:{kind};base64," + base64.b64encode(path.read_bytes()).decode()
        url = self._call("/media/upload", {"file": data, "fileName": path.name}).get("url")
        if not str(url).startswith("https://"):
            raise WeekError(f"Ayrshare did not return a media URL for {path.name}")
        return url

    def post(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._call("/post", body)


def client(env_file: Path = Path("/etc/bau/platforms.env")) -> Ayrshare:
    from .tiktok import _env_file
    key = {**_env_file(env_file), **os.environ}.get("AYRSHARE_API_KEY")
    if not key:
        raise WeekError("set AYRSHARE_API_KEY (on the laptop: /etc/bau/platforms.env, "
                        "brought over with bau keys import)")
    return Ayrshare(key)
