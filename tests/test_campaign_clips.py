"""Clips for paid clipping campaigns (src/bau/clips.py). The downloader is faked; ffmpeg and
ffprobe are real when this computer has them, so the moment-finding and the vertical cut are
proven on real sound and video."""

import json
import shutil
import subprocess

import pytest

from bau import clips as C
from bau import watch

STREAM = "https://www.twitch.tv/videos/111"
CHANNEL = "https://www.twitch.tv/kaicenat"
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def campaign(home, **kw):
    args = dict(name="Kai Cenat GTA 6", url="https://contentrewards.com/c/campaigns/abc",
                sources=[CHANNEL], caption="Watch Kai Cenat live on Twitch",
                hashtags=["#GTA6", "#KaiCenat"], rate_per_1k=1.0, seconds=10, per_day=2)
    args.update(kw)
    return C.add_campaign(home, "human:owner", **args)


class FakeYtdlp:
    """yt-dlp answers like its JSON; downloads are made with real ffmpeg: a 260-second stream
    whose sound is quiet except a shout at 140-143 s."""

    def __init__(self, uploader="kaicenat", entries=(STREAM,)):
        self.uploader, self.entries, self.calls = uploader, list(entries), []

    def __call__(self, args, **kw):
        if args[0] != "yt-dlp":
            return subprocess.run(args, **kw)            # ffmpeg and ffprobe: the real ones
        self.calls.append(args)
        out = ""
        if "--flat-playlist" in args:
            out = json.dumps({"entries": [{"url": u} for u in self.entries]})
        elif "-J" in args:
            out = json.dumps({"webpage_url": args[-1], "extractor": "twitch:vod",
                              "uploader_id": self.uploader, "uploader": "Kai Cenat",
                              "title": "GTA 6 day 3", "upload_date": "20261121"})
        elif "ba/b" in args:
            target = args[args.index("-o") + 1].replace("%(ext)s", "wav")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                            "aevalsrc='if(between(t,140,143),0.8,0.01)*sin(2*PI*440*t)'"
                            ":s=16000:d=160", target], check=True)
        else:                                             # one section of the stream
            a, b = (float(x) for x in args[args.index("--download-sections") + 1][1:]
                    .split("-"))
            target = args[args.index("-o") + 1]
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                            f"testsrc=size=640x360:rate=15:d={b - a}", "-f", "lavfi", "-i",
                            f"sine=f=440:d={b - a}", "-c:v", "libx264", "-preset",
                            "ultrafast", "-c:a", "aac", "-shortest", target], check=True)
        return subprocess.CompletedProcess(args, 0, out, "")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(watch, "ytdlp", lambda: "yt-dlp")
    from bau import station
    monkeypatch.setattr(station, "is_station", lambda: False)
    return tmp_path


PUBLIC = lambda host: ["151.101.2.167"]  # noqa: E731


@pytest.fixture
def small(monkeypatch):
    """Tests about the rules, not the picture: tiny frames render in a moment (the first test
    proves the real 1080x1920)."""
    monkeypatch.setattr(C, "W", 108)
    monkeypatch.setattr(C, "H", 192)


@needs_ffmpeg
def test_the_loudest_moment_becomes_a_vertical_clip_with_the_briefs_words(home):
    campaign(home)
    fake = FakeYtdlp()
    made = C.make(home, "kai-cenat-gta-6", STREAM, fake, count=1, resolve=PUBLIC)
    assert len(made) == 1
    item = made[0]
    assert item["start"] <= 140 <= item["end"] and 9 <= item["seconds"] <= 11    # the shout
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height", "-of", "csv=p=0",
                            str(home / item["file"])], capture_output=True, text=True)
    assert probe.stdout.strip() == "1080,1920"
    assert "Watch Kai Cenat live on Twitch" in item["description"]
    assert "#GTA6 #KaiCenat" in item["description"] and item["title"].endswith("#ad")
    assert "Paid clip for the Kai Cenat GTA 6 clipping campaign" in item["description"]
    assert C.problems(home, item) == []
    # only the sound and the clip's own minutes were downloaded, never the whole stream
    sections = [a for a in fake.calls if "--download-sections" in a]
    assert len(sections) == 1 and not any("bv*" in a and "--download-sections" not in a
                                          for a in fake.calls)


@needs_ffmpeg
def test_the_same_stream_is_never_clipped_twice_at_the_same_moment(home, small):
    campaign(home)
    first = C.make(home, "kai-cenat-gta-6", STREAM, FakeYtdlp(), count=1, resolve=PUBLIC)[0]
    second = C.make(home, "kai-cenat-gta-6", STREAM, FakeYtdlp(), count=1, resolve=PUBLIC)
    assert all(s["end"] <= first["start"] or s["start"] >= first["end"] for s in second)


def test_footage_from_another_channel_is_refused(home):
    campaign(home)
    with pytest.raises(C.ClipError, match="brief's own channels"):
        C.make(home, "kai-cenat-gta-6", STREAM, FakeYtdlp(uploader="someoneelse"),
               resolve=PUBLIC)
    with pytest.raises(C.ClipError, match="only stream links"):
        C.make(home, "kai-cenat-gta-6", "https://example.com/v.mp4", FakeYtdlp(),
               resolve=PUBLIC)


def test_moments_are_the_loudest_seconds_far_apart_after_the_waiting_screen():
    levels = [(float(t), -60.0) for t in range(0, 1000)]
    for t, db in ((50, -1.0), (300, -5.0), (310, -4.0), (700, -6.0)):
        levels[t] = (float(t), db)
    got = C.moments(levels, seconds=40, count=3)
    peaks = sorted(round(a + 24) for a, _ in got)          # each clip starts 24 s before
    assert 310 in peaks and 700 in peaks                   # the two loudest moments
    assert 300 not in peaks                                # too close to 310: one clip
    assert 50 not in peaks                                 # the waiting screen is skipped
    assert len(got) == 3 and all(b - a == 40 for a, b in got)
    assert all(abs(x - y) >= 40 for x in peaks for y in peaks if x != y)


def test_only_the_owner_adds_a_campaign_and_only_with_the_briefs_channels(home):
    with pytest.raises(PermissionError):
        C.add_campaign(home, "agent:marketer", "x", "https://contentrewards.com/c/1",
                       [CHANNEL], "caption", [])
    with pytest.raises(C.ClipError, match="streamer's own channel"):
        campaign(home, sources=["https://example.com/streams"])
    with pytest.raises(C.ClipError, match="caption"):
        campaign(home, caption=" ")


class FakeYouTube:
    def __init__(self):
        self.sent = []

    def upload_short(self, video, title, description, tags, privacy, made_for_kids):
        self.sent.append((video.name, title, privacy, made_for_kids))
        return {"id": "v1", "url": "https://www.youtube.com/shorts/v1", "privacy": privacy}


@needs_ffmpeg
def test_a_clip_goes_up_once_on_the_owners_accept_and_never_for_kids(home, small):
    from bau.audit import AuditLog
    from bau.governor import Governor
    campaign(home)
    item = C.make(home, "kai-cenat-gta-6", STREAM, FakeYtdlp(), count=1, resolve=PUBLIC)[0]
    yt = FakeYouTube()
    with pytest.raises(PermissionError):
        C.post(home, item["clip_id"], yt, "agent:marketer", "public", False)
    with pytest.raises(C.ClipError, match="rated M"):
        C.post(home, item["clip_id"], yt, "human:owner", "public", True)
    out = C.post(home, item["clip_id"], yt, "human:owner", "unlisted", False)
    assert out["status"] == "POSTED" and out["result"]["url"].endswith("/v1")
    assert yt.sent == [(f"{item['clip_id']}.mp4", item["title"], "unlisted", False)]
    with pytest.raises(C.ClipError):
        C.post(home, item["clip_id"], yt, "human:owner", "public", False)   # once
    other = C.make(home, "kai-cenat-gta-6", STREAM, FakeYtdlp(), count=1, resolve=PUBLIC)[0]
    Governor(home, audit=AuditLog(home / "audit" / "chain.jsonl", key=b""),
             systemctl="").hold("test", by="human:owner")
    with pytest.raises(C.ClipError, match="HOLD"):
        C.post(home, other["clip_id"], yt, "human:owner", "public", False)


@needs_ffmpeg
def test_a_changed_clip_or_a_missing_hashtag_stops_it(home, small):
    campaign(home)
    item = C.make(home, "kai-cenat-gta-6", STREAM, FakeYtdlp(), count=1, resolve=PUBLIC)[0]
    (home / item["file"]).write_bytes(b"something else")
    assert "the clip changed after it was made" in C.problems(home, item)
    item["description"] = item["description"].replace("#KaiCenat", "")
    assert "a hashtag the brief asks for is missing" in C.problems(home, item)


@needs_ffmpeg
def test_the_autopilot_clips_new_streams_up_to_the_number_a_day(home, small, monkeypatch):
    import datetime as dt
    campaign(home, per_day=1)
    fake = FakeYtdlp(entries=(STREAM, "https://www.twitch.tv/videos/222"))
    now = dt.datetime(2026, 11, 24, 12, tzinfo=dt.UTC)
    monkeypatch.setattr(C, "_now", lambda: now)
    assert C.tick(home, fake, now, resolve=PUBLIC) == 1
    assert C.tick(home, fake, now, resolve=PUBLIC) == 0          # its one a day is made
    assert [i["source_url"] for i in C.review(home)] == [STREAM]
    later = now + dt.timedelta(days=1)
    monkeypatch.setattr(C, "_now", lambda: later)
    assert C.tick(home, fake, later, resolve=PUBLIC) == 1        # the next stream, next day
    assert {i["source_url"] for i in C.review(home)} == {STREAM, "https://www.twitch.tv/videos/222"}


def test_on_the_laptop_station_the_autopilot_clips_nothing(home, monkeypatch):
    from bau import station
    campaign(home)
    monkeypatch.setattr(station, "is_station", lambda: True)
    assert C.tick(home, FakeYtdlp()) == 0


@needs_ffmpeg
def test_each_clip_is_a_card_in_jarvis_with_the_owners_two_answers(home, small, monkeypatch):
    from bau import youtube
    from bau.assistant import Assistant
    campaign(home)
    a, b = C.make(home, "kai-cenat-gta-6", STREAM, FakeYtdlp(), count=2, resolve=PUBLIC)
    yt = FakeYouTube()
    monkeypatch.setattr(youtube, "YouTubeClient", lambda h=None: yt)
    j = Assistant(home)
    cards = {j.pending[c["id"]].args["clip"]: c for c in j.setup_waiting()
             if c["tool"] == "clip_post"}
    card = cards[a["clip_id"]]
    assert card["preview"] and not card["voice"]                  # click only, with the video
    assert [f["name"] for f in card["form"]["fields"]] == ["privacy", "kids"]
    assert "within 30 minutes" in card["summary"] and a["campaign_url"] in card["summary"]
    assert j.confirm(card["id"], True, "human:owner", choices={"privacy": "public"}).get(
        "retry")                                                   # kids not answered yet
    out = j.confirm(card["id"], True, "human:owner",
                    choices={"privacy": "public", "kids": "no"})
    assert out["done"] and "Submit that link" in out["result"]["said"]
    assert yt.sent[0][2:] == ("public", False)
    j.confirm(cards[b["clip_id"]]["id"], False, "human:owner")
    assert C.get(home, b["clip_id"])["status"] == "DROPPED"
    assert not (home / b["file"]).exists()                       # its file is removed too
