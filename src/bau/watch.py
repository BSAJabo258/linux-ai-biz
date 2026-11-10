"""Jarvis watches a video from a link (YouTube, Shorts, TikTok, Vimeo ...): he reads its
title, channel and description, and hears what is said in it.

The owner asked Jarvis about a YouTube Short and he said he could not watch videos
(2026-11-10). The words come from the video's own captions when it has them; otherwise only
the sound is downloaded and the local Whisper on 127.0.0.1:8767 (bau-voice) writes it down.
Nothing leaves this computer except the download itself. The local model reads text only, so
Jarvis says plainly that he hears a video but does not see its pictures.

yt-dlp (public domain, github.com/yt-dlp/yt-dlp) does the fetching; it is looked for on PATH
and in the usual places. Like read_page: http(s) only, never this computer or the home
network, every watch is audited with its purpose, and what comes back is data for the model,
never instructions."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import web

LISTEN_URL = "http://127.0.0.1:8767/listen"
MAX_LISTEN_S = 15 * 60              # longest stretch of sound sent to Whisper (CPU, ~minutes)
TEXT_CHARS = 12000                  # transcript kept; Jarvis trims more for the small model
DESC_CHARS = 1500
YTDLP_PLACES = ("~/.local/bin/yt-dlp", "/usr/local/bin/yt-dlp", "/usr/bin/yt-dlp",
                "/opt/bau/venv/bin/yt-dlp")
NOT_INSTALLED = ("the video downloader (yt-dlp) is not installed on this computer. The owner "
                 "installs it once: sudo apt install yt-dlp (or the newest release from "
                 "github.com/yt-dlp/yt-dlp into /usr/local/bin)")
VIDEO_HOSTS = ("youtube.com", "youtu.be", "tiktok.com", "vimeo.com", "instagram.com",
               "x.com", "twitter.com", "rumble.com")
EXTRACTORS = "youtube.*,tiktok.*,vimeo.*,instagram.*,twitter.*,rumble.*"
NOT_SEEN ="I hear and read this video; the local model cannot see its pictures."

Run = Callable[..., subprocess.CompletedProcess]


def ytdlp() -> str | None:
    found = shutil.which("yt-dlp")
    if found:
        return found
    for p in YTDLP_PLACES:
        p = os.path.expanduser(p)
        if os.access(p, os.X_OK):
            return p
    return None


def _call(run: Run, args: list[str], timeout: int) -> subprocess.CompletedProcess:
    try:
        r = run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise ValueError("the video site took too long to answer") from e
    if r.returncode != 0:
        lines = [x for x in (r.stderr or "").splitlines() if "ERROR" in x]
        raise ValueError("the video could not be fetched: "
                         + ((lines or (r.stderr or "").splitlines() or ["no reason given"])[-1]
                            .replace("ERROR: ", "")[:300]))
    return r


_TAG = re.compile(r"<[^>]+>")
_TIME = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?[.,]\d{3}\s+-->")


def vtt_text(vtt: str) -> str:
    """Caption file -> plain words. Auto-captions repeat each line as it scrolls; kept once."""
    out: list[str] = []
    for line in vtt.splitlines():
        line = line.strip()
        if (not line or line == "WEBVTT" or _TIME.match(line) or line.isdigit()
                or line.startswith(("Kind:", "Language:", "NOTE", "STYLE"))):
            continue
        line = _TAG.sub("", line).replace("&nbsp;", " ").replace("&amp;", "&").strip()
        if line and (not out or line != out[-1]) and line not in out[-3:]:
            out.append(line)
    return " ".join(out)


def _listen(wav: bytes) -> str:
    req = urllib.request.Request(LISTEN_URL, data=wav, method="POST",
                                 headers={"Content-Type": "audio/wav"})
    try:
        with urllib.request.urlopen(req, timeout=MAX_LISTEN_S) as r:
            return str(json.loads(r.read() or b"{}").get("text") or "")
    except OSError as e:
        raise ValueError("the local listening service (bau-voice) is not answering") from e


def watch(url: str, why: str, *, audit: Any = None, actor: str = "agent:jarvis",
          run: Run = subprocess.run, listen: Callable[[bytes], str] = _listen,
          resolve: Callable[[str], list[str]] = web._resolve,
          binary: str | None = None) -> dict[str, Any]:
    web._need_reason(why)
    url = (url or "").strip()
    host = (urllib.parse.urlsplit(url).hostname or "").rstrip(".").lower()
    if not any(host == h or host.endswith("." + h) for h in VIDEO_HOSTS):
        raise ValueError("only links to " + ", ".join(VIDEO_HOSTS) + " can be watched")
    web._check(url, resolve)                  # http(s), public addresses only
    exe = binary or ytdlp()
    if exe is None:
        raise ValueError(NOT_INSTALLED)
    # Only these sites' own extractors: yt-dlp's generic one would read any page a link or a
    # redirect points at, past the one address check above (security review, 2026-11-10).
    base = [exe, "--no-playlist", "--no-warnings", "--ignore-config", "--no-cache-dir",
            "--use-extractors", EXTRACTORS]
    meta = json.loads(_call(run, base + ["-J", "--skip-download", "--", url], 90).stdout)
    out: dict[str, Any] = {
        "title": meta.get("title") or "", "channel": meta.get("uploader") or
        meta.get("channel") or "", "link": meta.get("webpage_url") or url,
        "duration_s": meta.get("duration"), "uploaded": meta.get("upload_date") or "",
        "views": meta.get("view_count"),
        "description": (meta.get("description") or "")[:DESC_CHARS],
        "transcript": "", "words_from": "none", "sees_pictures": False, "note": NOT_SEEN}
    with tempfile.TemporaryDirectory(prefix="bau-watch-") as tmp:
        d = Path(tmp)
        if meta.get("subtitles") or meta.get("automatic_captions"):
            try:
                _call(run, base + ["--skip-download", "--write-subs", "--write-auto-subs",
                                   "--sub-langs", "en.*,en", "--sub-format", "vtt",
                                   "-o", str(d / "v.%(ext)s"), "--", url], 90)
            except ValueError:
                pass                          # no English captions: listen instead
            subs = sorted(d.glob("*.vtt"))
            if subs:
                out["transcript"] = vtt_text(subs[0].read_text("utf-8", "replace"))
                out["words_from"] = "the video's captions"
        if not out["transcript"]:
            _call(run, base + ["-f", "bestaudio/best", "-o", str(d / "a.%(ext)s"),
                               "--", url], 300)
            got = [p for p in d.iterdir() if p.name.startswith("a.")]
            if got:
                wav = d / "a16k.wav"
                _call(run, ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i",
                            str(got[0]), "-vn", "-ac", "1", "-ar", "16000",
                            "-t", str(MAX_LISTEN_S), str(wav)], 120)
                out["transcript"] = listen(wav.read_bytes()).strip()
                out["words_from"] = "listening to it (local Whisper)"
                if (meta.get("duration") or 0) > MAX_LISTEN_S:
                    out["words_from"] += f", first {MAX_LISTEN_S // 60} minutes"
    if not out["transcript"]:
        out["transcript_note"] = "no speech found (music only, or silent)"
    out["transcript"] = out["transcript"][:TEXT_CHARS]
    web._audit(audit, "video.watch", actor, {"url": url, "why": why[:300],
                                            "title": out["title"][:200],
                                            "words_from": out["words_from"]})
    return out


# A video link, or a bare YouTube id the owner typed after "shorts" / "youtube" / "video".
VIDEO_LINK = re.compile(
    r"https?://(?:www\.|m\.|vm\.)?(?:youtube\.com/(?:watch\?\S+|shorts/\S+|live/\S+)|"
    r"youtu\.be/\S+|tiktok\.com/\S+|vimeo\.com/\S+|instagram\.com/(?:reel|p)/\S+|"
    r"(?:x|twitter)\.com/\S+/status/\S+|rumble\.com/\S+)", re.I)
BARE_ID = re.compile(r"\b(?:shorts?|youtube|video|watch)\b\W+([A-Za-z0-9_-]{11})(?![\w-])",
                     re.I)


def video_url(text: str) -> str | None:
    m = VIDEO_LINK.search(text or "")
    if m:
        return m.group(0).rstrip(".,!?)'\"")
    m = BARE_ID.search(text or "")
    if m and re.search(r"[0-9_-]|[a-z][A-Z]", m.group(1)):    # an id, not an 11-letter word
        return f"https://www.youtube.com/shorts/{m.group(1)}"
    return None
