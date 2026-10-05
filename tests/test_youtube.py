import base64
import hashlib
import json
import urllib.parse
from pathlib import Path

import pytest
import yaml

from bau import kids, youtube
from bau.audit import AuditLog
from bau.platforms import PlatformRegistry
from bau.publishing import Hub

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class FakeYouTube(youtube.Http):
    """Google OAuth + YouTube Data API, enough to exercise the real client code."""

    def __init__(self, audited=True, flaky_put=0):
        self.calls, self.received, self.meta = [], b"", None
        self.audited, self.flaky = audited, flaky_put

    def request(self, method, url, headers, body=None, timeout=120):
        self.calls.append((method, url, headers, body))
        if url.startswith(youtube.TOKEN_URL):
            return 200, {}, json.dumps({"access_token": "at2", "expires_in": 3599,
                                        "scope": youtube.SCOPES}).encode()
        if "/channels?" in url:
            return 200, {}, json.dumps({"items": [{"id": "UC1", "snippet": {
                "title": "Tiny Tales", "customUrl": "@tinytales"}}]}).encode()
        if url.startswith(youtube.UPLOAD) and method == "POST":
            self.meta = json.loads(body)
            self.total = int(headers["X-Upload-Content-Length"])
            return 200, {"location": "https://upload.example/session/1"}, b""
        if url.startswith("https://upload.example/session/") and method == "PUT":
            rng = headers["Content-Range"]
            if rng.startswith("bytes */"):
                last = len(self.received) - 1
                return 308, ({"range": f"bytes=0-{last}"} if last >= 0 else {}), b""
            if self.flaky:
                self.flaky -= 1
                return 503, {}, b""
            start = int(rng.split()[1].split("-")[0])
            assert start == len(self.received), (start, len(self.received))
            self.received += body
            if len(self.received) < self.total:
                return 308, {"range": f"bytes=0-{len(self.received) - 1}"}, b""
            asked = self.meta["status"]["privacyStatus"]
            return 200, {}, json.dumps({"id": "vid123", "status": {
                "uploadStatus": "uploaded",
                "privacyStatus": asked if self.audited else "private"}}).encode()
        if "/videos?" in url:
            return 200, {}, json.dumps({"items": [{"status": {
                "uploadStatus": "processed", "privacyStatus": "public",
                "madeForKids": True}}]}).encode()
        return 404, {}, b"{}"


def setup(home, size=1000, ai=True, **http):
    PlatformRegistry(home).upsert(yaml.safe_load((EXAMPLES / "platform-youtube.yaml")
                                                 .read_text()))
    arts = home / "artifacts" / "videos"
    arts.mkdir(parents=True, exist_ok=True)
    video = arts / f"ep{size}.mp4"
    video.write_bytes(bytes(range(256)) * (size // 256) + b"v" * (size % 256))
    if ai:
        (arts / (video.name + ".provenance.json")).write_text(json.dumps({
            "artifact_id": "a1", "media_type": "video", "ai_generated": True,
            "ai_assisted": False, "human_authored": False, "human_modified": True,
            "model_id": "m", "visible_disclosure_text": "AI-GENERATED VIDEO",
            "artifact_sha256": hashlib.sha256(video.read_bytes()).hexdigest()}))
    client = youtube.YouTubeClient(home, http=FakeYouTube(**http), creds=("cid", "cs"))
    client.tokens.save({"access_token": "at", "refresh_token": "rt", "expires_in": 3600})
    q = youtube.YouTubeQueue(home, AuditLog(home / "audit" / "chain.jsonl", key=b""))
    return video, client, q


CLEAN = "Benny the Bear Learns to Count to Ten"


def test_kids_scan_flags_what_coppa_and_youtube_care_about():
    assert kids.scan(CLEAN, "A gentle counting song with Benny and his friends.",
                     ["counting", "preschool"]) == []
    found = {i["issue"] for i in kids.scan(
        "SCARY PEPPA PIG PRANK!!!", "Comment your name below and visit www.toys-now.com. "
        "Ask your parents to buy it now! Like and subscribe!")}
    assert found == {"personal_info", "external_link", "engagement_bait", "purchase_pressure",
                     "unsuitable_theme", "franchise", "clickbait"}
    assert kids.near_duplicate("Benny the Bear learns to count to ten",
                               [("yt_a", CLEAN)]) == "yt_a"
    assert kids.near_duplicate("Benny the Bear visits the farm", [("yt_a", CLEAN)]) is None


def test_clean_kids_video_queues_ok(tmp_path, engine):
    video, client, q = setup(tmp_path)
    item = q.add(video, CLEAN, "human:owner", "A gentle counting song.", ["counting"],
                 kids=True, engine=engine)
    assert item.checks["ok"], item.checks
    assert item.is_aigc and item.kids and item.checks["warnings"] == []


def test_kids_rules_block_and_explain(tmp_path, engine):
    video, client, q = setup(tmp_path)
    bad = q.add(video, "Peppa Pig Scary Prank", "human:owner",
                "Tell us your name in the comments! www.example.com", kids=True,
                engine=engine)
    assert not bad.checks["ok"]
    text = " | ".join(bad.checks["problems"])
    for want in ("personal information", "off YouTube", "someone else owns",
                 "not suitable"):
        assert want in text, want
    # a licence clears the character rule only
    lic = q.add(video, "Peppa Pig counts to ten", "human:owner", kids=True, licensed=True,
                engine=engine)
    assert lic.checks["ok"], lic.checks
    paid = q.add(video, "Benny tries a new cereal", "human:owner", kids=True,
                 paid_promotion=True, engine=engine)
    assert any("paid promotion" in p for p in paid.checks["problems"])
    # the same story twice is a warning about YouTube's mass-produced content rule
    q.add(video, CLEAN, "human:owner", kids=True, engine=engine)
    again = q.add(video, "Benny the bear learns to count to ten", "human:owner", kids=True,
                  engine=engine)
    assert again.checks["ok"] and any("mass-produced" in w for w in again.checks["warnings"])


def test_upload_is_resumable_and_sets_made_for_kids(tmp_path, engine, monkeypatch):
    monkeypatch.setattr(youtube, "CHUNK", 256 * 1024)
    video, client, q = setup(tmp_path, size=700_000, flaky_put=1)
    item = q.add(video, CLEAN, "human:owner", "A counting song.", ["counting"], kids=True,
                 category_id="27", engine=engine)
    with pytest.raises(PermissionError):
        q.post(item, client, "agent:x", "public", True, True)
    with pytest.raises(youtube.YouTubeError, match="watch the whole video"):
        q.post(item, client, "human:owner", "public", True, watched=False)
    with pytest.raises(youtube.YouTubeError, match="must stay"):
        q.post(item, client, "human:owner", "public", False, watched=True)
    done = q.post(item, client, "human:owner", "public", True, watched=True)
    fake = client.http
    assert fake.received == video.read_bytes()
    puts = [h["Content-Range"] for m, u, h, b in fake.calls if m == "PUT"]
    assert puts[0] == "bytes 0-262143/700000" and "bytes */700000" in puts   # 503 -> probe
    st = fake.meta["status"]
    assert st == {"privacyStatus": "public", "selfDeclaredMadeForKids": True,
                  "containsSyntheticMedia": True, "embeddable": True, "license": "youtube"}
    assert fake.meta["snippet"]["categoryId"] == "27"
    assert done.status == "POSTED" and done.result["url"] == "https://youtu.be/vid123"
    with pytest.raises(youtube.YouTubeError, match="only once"):
        q.post(done, client, "human:owner", "public", True, True)
    events = [json.loads(x)["event"] for x in
              (tmp_path / "audit" / "chain.jsonl").read_text().splitlines()]
    assert "approval.granted" in events and "youtube.published" in events


def test_unaudited_project_and_daily_cap_and_paid_promotion(tmp_path, engine):
    video, client, q = setup(tmp_path, audited=False)
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "youtube.yaml").write_text("max_uploads_per_day: 1\n")
    q = youtube.YouTubeQueue(tmp_path, q.audit)
    a = q.add(video, "How rainbows form", "human:owner", engine=engine)
    b = q.add(video, "Why the sky is blue", "human:owner", engine=engine)
    with pytest.raises(youtube.YouTubeError, match="kids checks never ran"):
        q.post(a, client, "human:owner", "public", made_for_kids=True)
    done = q.post(a, client, "human:owner", "public", made_for_kids=False)
    assert done.result["privacyStatus"] == "private" and "audit" in done.result["note"]
    with pytest.raises(youtube.YouTubeError, match="daily limit"):
        q.post(b, client, "human:owner", "public", made_for_kids=False)
    c = q.add(video, "Our sponsor's new app", "human:owner", paid_promotion=True,
              engine=engine)
    q.cfg["max_uploads_per_day"] = 5
    with pytest.raises(youtube.YouTubeError, match="paid promotion"):
        q.post(c, client, "human:owner", "public", made_for_kids=False)


def test_review_screen_asks_audience_and_privacy_without_defaults(tmp_path, engine):
    video, client, q = setup(tmp_path)
    q.add(video, "How rainbows form", "human:owner", engine=engine)
    q.add(video, CLEAN, "human:owner", kids=True, engine=engine)
    said, answers = [], iter(["", "n", "n", "x", "2", "y",      # adult video: unlisted
                              "n",                             # kids: not watched -> skip
                              ])
    done = youtube.review(q, client, "human:owner", ask=lambda p: next(answers),
                          say=said.append)
    assert [d.status for d in done] == ["POSTED"]
    assert client.http.meta["status"]["privacyStatus"] == "unlisted"
    assert client.http.meta["status"]["selfDeclaredMadeForKids"] is False
    assert any("MADE FOR KIDS" in s for s in said) and any("Watch it first" in s for s in said)
    assert any("Tiny Tales" in s for s in said)


def test_oauth_uses_pkce_s256_and_offline_access(tmp_path):
    v, c = youtube.pkce_pair()
    assert c == base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()
    client = youtube.YouTubeClient(tmp_path, http=FakeYouTube(), creds=("cid", "cs"))
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(
        client.authorize_url("http://127.0.0.1:3456/", "st", c)).query))
    assert q["code_challenge_method"] == "S256" and q["access_type"] == "offline"
    assert "youtube.upload" in q["scope"]
    client.tokens.save({"access_token": "old", "refresh_token": "rt", "expires_in": 0})
    assert client.access_token() == "at2"                  # refreshed
    assert client.tokens.load()["refresh_token"] == "rt"   # kept: Google doesn't resend it
    assert oct(client.tokens.path.stat().st_mode)[-3:] == "600"


def test_hub_routes_kids_only_to_youtube_and_jarvis_posts_through_it(tmp_path, engine):
    from test_assistant import make
    video, client, q = setup(tmp_path)
    hub = Hub(tmp_path, q.audit)
    out = hub.queue(video, ["youtube", "tiktok"], "human:owner", title=CLEAN, kids=True,
                    engine=engine)
    assert out[0]["platform"] == "youtube" and out[0]["ok"]
    assert out[1] == {"platform": "tiktok", "skipped": hub.adapter("tiktok").kids_note}
    with pytest.raises(ValueError, match="unknown platform"):
        hub.adapter("myspace")
    pending = hub.pending()
    assert [p["platform"] for p in pending] == ["youtube"] and pending[0]["made_for_kids"]
    a = make(tmp_path, clients={"youtube": client}, script=[
        {"tool": "post_video", "input": {"platform": "youtube", "item_id": out[0]["item_id"],
                                         "privacy": "public"}}, "It's on your screen."])
    r = a.ask("post the kids episode")
    p = r.pending[0]
    assert "Tiny Tales" in p["summary"] and "MADE FOR KIDS" in p["summary"] and p["preview"]
    assert [f["name"] for f in p["form"]["fields"]] == ["watched", "privacy"]
    assert client.http.meta is None                          # nothing uploaded yet
    assert a.confirm(p["id"], True, "human:owner", {"privacy": "public"})["retry"]
    res = a.confirm(p["id"], True, "human:owner", {"watched": "yes", "privacy": "unlisted"})
    assert res["done"], res
    assert client.http.meta["status"]["selfDeclaredMadeForKids"] is True
    assert client.http.meta["status"]["privacyStatus"] == "unlisted"
