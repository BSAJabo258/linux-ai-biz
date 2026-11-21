"""Jarvis watches a video from a link (src/bau/watch.py). The owner asked about a YouTube
Short and Jarvis said he could not watch videos (2026-11-10). Written before the code: the
words come from the video's captions, else from the local Whisper hearing its sound; the
local model is told plainly it does not see the pictures; never this computer or the home
network; every watch audited with its purpose; yt-dlp missing is said, never faked. All
fakes: no network, no yt-dlp, no Whisper."""

import json
import subprocess
from pathlib import Path

import pytest

from bau import watch as W
from bau.audit import AuditLog

URL = "https://www.youtube.com/shorts/j2WbZSPYKQI"
PUBLIC = lambda host: ["142.250.80.46"]  # noqa: E731
VTT = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:02.000
<c>meet</c> the automaton

00:00:01.000 --> 00:00:03.000
meet the automaton
it makes money or it dies
"""


class FakeYtdlp:
    def __init__(self, captions=True, fail=""):
        self.calls, self.captions, self.fail = [], captions, fail

    def __call__(self, args, **kw):
        self.calls.append(args)
        if self.fail:
            return subprocess.CompletedProcess(args, 1, "", f"ERROR: {self.fail}")
        if "-J" in args:
            meta = {"title": "Automaton AI", "uploader": "BassForge", "duration": 42,
                    "webpage_url": URL, "description": "an agent that pays for itself",
                    "automatic_captions": {"en": [{}]} if self.captions else {}}
            return subprocess.CompletedProcess(args, 0, json.dumps(meta), "")
        out = Path(args[args.index("-o") + 1]) if "-o" in args else Path(args[-1])
        if "--write-subs" in args:
            (out.parent / "v.en.vtt").write_text(VTT)
        elif "bestaudio/best" in args:
            (out.parent / "a.webm").write_bytes(b"sound")
        elif args[0] == "ffmpeg":
            Path(args[-1]).write_bytes(b"RIFFwav")
        return subprocess.CompletedProcess(args, 0, "", "")


def test_the_words_come_from_the_captions_and_the_watch_is_audited(tmp_path):
    audit = AuditLog(tmp_path / "a.jsonl")
    out = W.watch(URL, "the owner asked", audit=audit, run=FakeYtdlp(), resolve=PUBLIC,
                  binary="yt-dlp", listen=lambda b: pytest.fail("captions were there"))
    assert out["title"] == "Automaton AI" and out["channel"] == "BassForge"
    assert out["transcript"] == "meet the automaton it makes money or it dies"
    assert out["words_from"] == "the video's captions"
    assert out["sees_pictures"] is False and "cannot see" in out["note"]
    row = json.loads((tmp_path / "a.jsonl").read_text().splitlines()[-1])
    assert row["event"] == "video.watch" and row["data"]["why"] == "the owner asked"


def test_without_captions_the_local_whisper_hears_it():
    fake, heard = FakeYtdlp(captions=False), []
    out = W.watch(URL, "owner", run=fake, resolve=PUBLIC, binary="yt-dlp",
                  listen=lambda b: heard.append(b) or "hello from the short")
    assert heard == [b"RIFFwav"] and out["transcript"] == "hello from the short"
    assert out["words_from"].startswith("listening to it")
    ff = next(c for c in fake.calls if c[0] == "ffmpeg")
    assert ff[ff.index("-ar") + 1] == "16000" and str(W.MAX_LISTEN_S) in ff


@pytest.mark.parametrize("url", ["http://127.0.0.1:8080/x", "http://192.168.1.5/v",
                                 "file:///etc/passwd", "http://router.lan/v"])
def test_never_this_computer_or_the_home_network(url):
    fake = FakeYtdlp()
    with pytest.raises(ValueError):
        W.watch(url, "owner", run=fake, resolve=lambda h: ["192.168.1.5"], binary="yt-dlp")
    assert fake.calls == []


def test_a_reason_is_needed_and_a_missing_downloader_is_said(monkeypatch):
    with pytest.raises(ValueError, match="why"):
        W.watch(URL, " ", run=FakeYtdlp(), resolve=PUBLIC, binary="yt-dlp")
    monkeypatch.setattr(W, "ytdlp", lambda: None)
    with pytest.raises(ValueError, match="yt-dlp"):
        W.watch(URL, "owner", run=FakeYtdlp(), resolve=PUBLIC)


def test_the_sites_error_is_passed_on_plainly():
    with pytest.raises(ValueError, match="Video unavailable"):
        W.watch(URL, "owner", run=FakeYtdlp(fail="[youtube] x: Video unavailable"),
                resolve=PUBLIC, binary="yt-dlp")


@pytest.mark.parametrize("text,url", [
    ("watch https://youtube.com/shorts/j2WbZSPYKQI?si=abc.",
     "https://youtube.com/shorts/j2WbZSPYKQI?si=abc"),
    ("what is in https://youtu.be/dQw4w9WgXcQ", "https://youtu.be/dQw4w9WgXcQ"),
    ("youtube shorts j2WbZSPYKQI automaton AI", URL),
    ("this video informatics is great", None),          # an 11-letter word, not an id
    ("what's broken today", None),
])
def test_video_links_are_found_in_the_owners_words(text, url):
    assert W.video_url(text) == url


def test_auto_captions_scrolling_lines_are_kept_once():
    assert W.vtt_text(VTT).count("meet the automaton") == 1


@pytest.mark.parametrize("url", ["https://example.com/page", "https://youtube.com.evil.test/x",
                                 "https://notyoutube.com/watch?v=j2WbZSPYKQI"])
def test_only_known_video_sites_and_only_their_own_extractors(url):
    fake = FakeYtdlp()
    with pytest.raises(ValueError, match="only links to"):
        W.watch(url, "owner", run=fake, resolve=PUBLIC, binary="yt-dlp")
    assert fake.calls == []
    W.watch("https://m.youtube.com/watch?v=j2WbZSPYKQI", "owner", run=fake, resolve=PUBLIC,
            binary="yt-dlp")
    for c in fake.calls:
        if c[0] == "yt-dlp":
            assert c[c.index("--use-extractors") + 1] == W.EXTRACTORS
            assert "generic" not in W.EXTRACTORS
