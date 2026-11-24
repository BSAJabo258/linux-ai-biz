"""Clips for paid clipping campaigns (the owner's ask, 2026-11-24: GTA 6 clips "making a bunch
of money"). See docs/CLIPS.md.

How the money works (read 2026-11-24 on contentrewards.com): a streamer or brand funds a
campaign; clippers post short clips of that campaign's own footage to TikTok, Instagram Reels or
YouTube Shorts and are paid per 1,000 verified views from the campaign's budget ($0.50 to $1.50
per 1,000 on the GTA 6 campaigns that day, with a cap per clip). The brief names the only footage
allowed ("Only use KreekCraft's official GTA 6 livestreams and stream replays"), a caption and
hashtags every clip must carry, sometimes an overlay, and forbids "Stolen clips, reuploads,
fabricated context, fake reactions, and misleading titles". A clip is paid only if its link is
submitted in the campaign within 30 minutes of posting, from an account connected there
(help.contentrewards.com: "Connect your social accounts"; contentrewards.com/articles/
get-paid-to-clip-videos). Content Rewards showed no way for software to submit.

Why campaigns and not BAU's own GTA channel: Rockstar's policy (support.rockstargames.com,
"Policy on posting copyrighted Rockstar Games material", updated 2025-01-10) allows fans'
gameplay footage for non-commercial use only ("'Non-commercial' means that you don't make money
through the game footage you post") and takes down pre-release footage and cheating or exploit
videos; YouTube's reused-content policy keeps clip compilations "with little or no narrative"
out of ad money. A campaign pays from the streamer's own budget for clips of his own streams.

What runs by itself (the autopilot, `tick`): for each campaign the owner added, the newest
stream from the brief's own channels; its sound only, to find the loudest moments; just those
minutes of video; a vertical 1080x1920 clip each, with the campaign's overlay. Every clip waits
on a card: the owner picks the privacy and answers made-for-kids, Accept uploads it to YouTube
Shorts and the card gives the campaign link to submit it within 30 minutes. Nothing is posted
without that Accept: an unsubmitted clip earns nothing.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import secrets
import subprocess
import tempfile
import urllib.parse
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from .audit import AuditLog
from .home import atomic_write_json

SOURCE_HOSTS = ("youtube.com", "youtu.be", "twitch.tv", "kick.com")
EXTRACTORS = "youtube.*,twitch.*,kick.*"
CLIP_SECONDS = 40
MAX_SECONDS = 180                 # YouTube: a vertical video up to three minutes is a Short
PER_DAY = 3
SKIP_START = 120                  # a stream's first minutes are its waiting screen
W, H = 1080, 1920
AD = "#ad"

Run = Callable[..., subprocess.CompletedProcess]


class ClipError(ValueError):
    pass


def _dir(home: Path) -> Path:
    return home / "clips"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _audit(home: Path) -> AuditLog:
    return AuditLog(home / "audit" / "chain.jsonl")


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---------------------------------------------------------------- campaigns (the owner's)
def campaigns(home: Path) -> dict[str, dict[str, Any]]:
    p = _dir(home) / "campaigns.yaml"
    return (yaml.safe_load(p.read_text()) or {}) if p.exists() else {}


def _source_ok(url: str) -> bool:
    u = urllib.parse.urlsplit(url)
    host = (u.hostname or "").lower()
    return u.scheme == "https" and any(host == h or host.endswith("." + h)
                                       for h in SOURCE_HOSTS)


def add_campaign(home: Path, by: str, name: str, url: str, sources: list[str], caption: str,
                 hashtags: list[str], rate_per_1k: float = 0.0, overlay: str = "",
                 seconds: int = CLIP_SECONDS, per_day: int = PER_DAY) -> dict[str, Any]:
    """The owner copies the brief: which channels' streams, the caption and hashtags every
    clip must carry, the overlay file (put in BAU_HOME/clips/overlays)."""
    if not by.startswith("human:"):
        raise PermissionError("only the owner adds a campaign (he joins it and reads its brief)")
    if not url.startswith("https://"):
        raise ClipError("the campaign's own link, starting https://")
    sources = [s.strip().rstrip("/") for s in sources if s.strip()]
    if not sources or not all(_source_ok(s) for s in sources):
        raise ClipError("sources: the streamer's own channel links from the brief (https, "
                        "on " + ", ".join(SOURCE_HOSTS) + ")")
    if not caption.strip():
        raise ClipError("the caption the brief asks every clip to carry")
    if not 5 <= int(seconds) <= MAX_SECONDS:
        raise ClipError(f"a clip is 5 to {MAX_SECONDS} seconds")
    if overlay and not (_dir(home) / "overlays" / Path(overlay).name).is_file():
        raise ClipError(f"put the overlay in {_dir(home) / 'overlays'} first")
    cid = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "campaign"
    data = campaigns(home)
    data[cid] = {"name": name.strip(), "url": url, "sources": sources,
                 "caption": caption.strip(),
                 "hashtags": [h if h.startswith("#") else "#" + h for h in hashtags if h],
                 "rate_per_1k": float(rate_per_1k), "overlay": Path(overlay).name if overlay
                 else "", "seconds": int(seconds), "per_day": max(1, int(per_day)),
                 "added_by": by, "added_at": _now().isoformat(timespec="seconds")}
    p = _dir(home) / "campaigns.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=True))
    _audit(home).append("clips.campaign_added", by, {"campaign": cid, "url": url})
    return data[cid]


def from_campaign(camp: dict[str, Any], meta: dict[str, Any]) -> bool:
    """Is this video one of the brief's own channels' streams? (by what the site says it is)"""
    seen = [meta.get(k) or "" for k in ("webpage_url", "channel_url", "uploader_url")]
    if meta.get("uploader_id") and "twitch" in (meta.get("extractor") or "").lower():
        seen.append(f"https://www.twitch.tv/{meta['uploader_id']}")
    seen = [s.lower().rstrip("/") for s in seen if s]
    return any(s == src.lower() or s.startswith(src.lower() + "/") for s in seen
               for src in camp["sources"])


# ---------------------------------------------------------------- the downloader
def _ytdlp(run: Run, args: list[str], timeout: int) -> subprocess.CompletedProcess:
    from .watch import NOT_INSTALLED, _call, ytdlp
    exe = ytdlp()
    if exe is None:
        raise ClipError(NOT_INSTALLED)
    try:
        return _call(run, [exe, "--no-warnings", "--ignore-config", "--no-cache-dir",
                           "--use-extractors", EXTRACTORS, *args], timeout)
    except ValueError as e:
        raise ClipError(str(e)) from None


def latest(camp: dict[str, Any], run: Run = subprocess.run, n: int = 3) -> list[str]:
    """The newest videos on the brief's channels (links only, nothing downloaded)."""
    out: list[str] = []
    for src in camp["sources"]:
        data = json.loads(_ytdlp(run, ["--flat-playlist", "--playlist-end", str(n), "-J",
                                       "--", src], 120).stdout or "{}")
        for e in data.get("entries") or []:
            link = e.get("url") or e.get("webpage_url")
            if link and link.startswith("https://") and link not in out:
                out.append(link)
    return out


# ---------------------------------------------------------------- finding the moments
_RMS = re.compile(r"pts_time:([\d.]+)|lavfi\.astats\.Overall\.RMS_level=(-?[\d.]+|-inf)")


def loudness(audio: Path, run: Run = subprocess.run) -> list[tuple[float, float]]:
    """(second, loudness in dB) for each second of the sound, from ffmpeg's own meter."""
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(audio), "-af",
             "aresample=16000,asetnsamples=n=16000,astats=metadata=1:reset=1,"
             "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-", "-f", "null", "-"],
            capture_output=True, text=True, timeout=3600)
    if r.returncode != 0:
        raise ClipError("ffmpeg could not read the sound: " + (r.stderr or "")[-300:])
    out, t = [], None
    for m in _RMS.finditer(r.stdout):
        if m.group(1) is not None:
            t = float(m.group(1))
        elif t is not None:
            out.append((t, -120.0 if m.group(2) == "-inf" else float(m.group(2))))
            t = None
    return out


def moments(levels: list[tuple[float, float]], seconds: int, count: int,
            skip: float = SKIP_START) -> list[tuple[float, float]]:
    """The loudest seconds (a shout, a crash, the chat going wild), each far from the others;
    every clip starts a little before its peak so the moment has its run-up."""
    end = max((t for t, _ in levels), default=0.0)
    picked: list[float] = []
    for t, _ in sorted((x for x in levels if skip <= x[0] <= end - 5), key=lambda x: -x[1]):
        if all(abs(t - p) >= seconds for p in picked):
            picked.append(t)
        if len(picked) == count:
            break
    out = []
    for p in sorted(picked):
        start = max(0.0, p - seconds * 0.6)
        out.append((round(start, 1), round(min(start + seconds, end), 1)))
    return out


# ---------------------------------------------------------------- making the clip
def render(src: Path, out: Path, seconds: float, overlay: Path | None = None,
           run: Run = subprocess.run) -> None:
    """Vertical 1080x1920: the stream in the middle at full width over a blurred copy of
    itself, the campaign's overlay on top when it has one."""
    graph = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
             f"boxblur=20:2[bg];[0:v]scale={W}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[v0]")
    args = ["ffmpeg", "-hide_banner", "-nostats", "-y", "-i", str(src)]
    if overlay is not None:
        args += ["-i", str(overlay)]
        graph += f";[1:v]scale={W}:-2[ov];[v0][ov]overlay=0:0[v]"
    else:
        graph += ";[v0]copy[v]"
    args += ["-filter_complex", graph, "-map", "[v]", "-map", "0:a?", "-t", f"{seconds:.1f}",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)]
    r = run(args, capture_output=True, text=True, timeout=1800)
    if r.returncode != 0 or not out.is_file():
        raise ClipError("ffmpeg could not make the clip: " + (r.stderr or "")[-300:])


def duration(video: Path, run: Run = subprocess.run) -> float:
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
             "default=nw=1:nk=1", str(video)], capture_output=True, text=True, timeout=60)
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise ClipError("ffprobe could not read the clip") from None


# ---------------------------------------------------------------- the queue
def _qdir(home: Path) -> Path:
    return _dir(home) / "queue"


def items(home: Path) -> list[dict[str, Any]]:
    d = _qdir(home)
    if not d.is_dir():
        return []
    return sorted((json.loads(p.read_text()) for p in d.glob("cl_*.json")),
                  key=lambda i: i["created_at"])


def _save(home: Path, item: dict[str, Any]) -> None:
    atomic_write_json(_qdir(home) / f"{item['clip_id']}.json", item)


def get(home: Path, clip_id: str) -> dict[str, Any] | None:
    return next((i for i in items(home) if i["clip_id"] == clip_id), None)


def review(home: Path) -> list[dict[str, Any]]:
    return [i for i in items(home) if i["status"] == "REVIEW"]


def words(camp: dict[str, Any], meta: dict[str, Any]) -> tuple[str, str, list[str]]:
    """Title, description and tags: the brief's caption and hashtags, the paid-clip disclosure
    (the FTC's endorsement guides: a material connection said plainly), never a made-up claim."""
    who = meta.get("uploader") or meta.get("channel") or camp["name"]
    day = (meta.get("upload_date") or "")
    when = f" ({day[:4]}-{day[4:6]}-{day[6:]})" if len(day) == 8 else ""
    title = f"{who} stream moment{when} {AD}"
    desc = "\n".join([f"Paid clip for the {camp['name']} clipping campaign.", camp["caption"],
                      " ".join(camp["hashtags"]),
                      f"From {who}'s stream: {meta.get('webpage_url', '')}"])
    return title[:100], desc, [h.lstrip("#") for h in camp["hashtags"]][:30]


def problems(home: Path, item: dict[str, Any]) -> list[str]:
    """Why this clip must not go up (empty: it may). The brief's rules and the disclosure."""
    out = []
    camp = campaigns(home).get(item["campaign"])
    if camp is None:
        return ["its campaign was removed"]
    p = home / item["file"]
    if not p.is_file():
        return ["the clip file is gone"]
    if _sha256(p) != item["sha256"]:
        out.append("the clip changed after it was made")
    if not item.get("from_campaign"):
        out.append("its footage is not from the brief's own channels")
    if camp["caption"] not in item["description"]:
        out.append("the brief's caption is missing")
    if any(h not in item["description"] for h in camp["hashtags"]):
        out.append("a hashtag the brief asks for is missing")
    if AD not in item["title"] or "Paid clip" not in item["description"]:
        out.append("the paid-clip disclosure is missing")
    if item["seconds"] > MAX_SECONDS:
        out.append(f"longer than a Short ({MAX_SECONDS} s)")
    return out


def make(home: Path, cid: str, url: str, run: Run = subprocess.run, count: int = 1,
         resolve: Any = None) -> list[dict[str, Any]]:
    """One stream: its sound, its loudest moments, a clip of each, on cards."""
    from . import web
    camp = campaigns(home).get(cid)
    if camp is None:
        raise ClipError(f"no campaign {cid!r}: bau clips campaign add")
    if not _source_ok(url):
        raise ClipError("only stream links on " + ", ".join(SOURCE_HOSTS))
    web._check(url, resolve or web._resolve)             # http(s), public addresses only
    meta = json.loads(_ytdlp(run, ["-J", "--skip-download", "--no-playlist", "--", url],
                             120).stdout or "{}")
    if not from_campaign(camp, meta):
        raise ClipError("this video is not from the brief's own channels; campaigns pay only "
                        "for clips of their own streams")
    done = [i for i in items(home) if i["source_url"] == (meta.get("webpage_url") or url)]
    made: list[dict[str, Any]] = []
    out_dir = _dir(home) / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bau-clips-") as tmp:
        t = Path(tmp)
        _ytdlp(run, ["-f", "ba/b", "--no-playlist", "-o", str(t / "sound.%(ext)s"), "--", url],
               3600)
        sound = next(iter(sorted(t.glob("sound.*"))), None)
        if sound is None:
            raise ClipError("the stream's sound did not download")
        want = moments(loudness(sound, run), camp["seconds"], count + len(done))
        taken = [(i["start"], i["end"]) for i in done]
        want = [w for w in want if all(w[1] <= a or w[0] >= b for a, b in taken)][:count]
        overlay = (_dir(home) / "overlays" / camp["overlay"]) if camp["overlay"] else None
        for start, end in want:
            part = t / f"part-{int(start)}.mp4"
            _ytdlp(run, ["-f", "bv*[height<=1080]+ba/b[height<=1080]", "--no-playlist",
                         "--download-sections", f"*{start}-{end}", "--merge-output-format",
                         "mp4", "-o", str(part), "--", url], 1800)
            clip_id = "cl_" + secrets.token_hex(5)
            out = out_dir / f"{clip_id}.mp4"
            render(part, out, end - start, overlay, run)
            title, desc, tags = words(camp, meta)
            item = {"clip_id": clip_id, "campaign": cid, "campaign_url": camp["url"],
                    "source_url": meta.get("webpage_url") or url,
                    "source_title": (meta.get("title") or "")[:200], "from_campaign": True,
                    "start": start, "end": end, "seconds": round(duration(out, run), 1),
                    "file": str(out.relative_to(home)), "sha256": _sha256(out),
                    "title": title, "description": desc, "tags": tags, "status": "REVIEW",
                    "created_at": _now().isoformat(timespec="seconds"), "result": {}}
            _save(home, item)
            _audit(home).append("clips.made", "process:clips", {"clip": clip_id,
                                                                "campaign": cid})
            made.append(item)
    return made


def tick(home: Path, run: Run = subprocess.run, now: dt.datetime | None = None,
         resolve: Any = None) -> int:
    """The autopilot's turn: for each campaign under its number a day, the newest stream not
    clipped yet. Returns how many clips now wait on cards."""
    from .governor import hold_reason
    from .station import is_station
    if is_station() or hold_reason(home) is not None:
        return 0
    day = (now or _now()).date().isoformat()
    made = 0
    for cid, camp in campaigns(home).items():
        today = sum(1 for i in items(home) if i["campaign"] == cid
                    and i["created_at"][:10] == day)
        if today >= camp["per_day"]:
            continue
        clipped = {i["source_url"] for i in items(home) if i["campaign"] == cid}
        try:
            fresh = [u for u in latest(camp, run) if u not in clipped]
            if fresh:
                made += len(make(home, cid, fresh[0], run, count=camp["per_day"] - today,
                                 resolve=resolve))
        except ClipError as e:
            _audit(home).append("clips.skipped", "process:clips",
                                {"campaign": cid, "why": str(e)[:300]})
    return made


def post(home: Path, clip_id: str, client: Any, by: str, privacy: str,
         made_for_kids: bool) -> dict[str, Any]:
    """Only on the owner's Accept: up to YouTube Shorts once; then he submits the link."""
    from .governor import hold_reason
    if not by.startswith("human:"):
        raise PermissionError("only the owner posts a clip")
    if (why := hold_reason(home)) is not None:
        raise ClipError(f"BAU is on HOLD ({why}): nothing is posted until it is released")
    item = get(home, clip_id)
    if item is None or item["status"] != "REVIEW":
        raise ClipError(f"{clip_id} is not waiting to be posted")
    if made_for_kids:
        raise ClipError("GTA 6 is rated M: these clips are not made for kids")
    if bad := problems(home, item):
        raise ClipError("; ".join(bad))
    item["status"] = "POSTING"                                   # never twice
    _save(home, item)
    try:
        out = client.upload_short(home / item["file"], item["title"], item["description"],
                                  item["tags"], privacy, made_for_kids=False)
    except Exception as e:
        item["status"], item["result"] = "FAILED", {"error": str(e)[:300]}
        _save(home, item)
        _audit(home).append("clips.failed", by, {"clip": clip_id})
        raise
    item.update(status="POSTED", posted_at=_now().isoformat(timespec="seconds"), result=out)
    _save(home, item)
    _audit(home).append("clips.posted", by, {"clip": clip_id, "url": out.get("url"),
                                             "privacy": privacy})
    return item


def drop(home: Path, clip_id: str, by: str) -> dict[str, Any]:
    if not by.startswith("human:"):
        raise PermissionError("only the owner drops a clip")
    item = get(home, clip_id)
    if item is None or item["status"] != "REVIEW":
        raise ClipError(f"{clip_id} is not waiting")
    item["status"] = "DROPPED"
    _save(home, item)
    (home / item["file"]).unlink(missing_ok=True)                # laptop disk is small
    _audit(home).append("clips.dropped", by, {"clip": clip_id})
    return item
