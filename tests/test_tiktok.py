import hashlib
import json
import shutil
import time
from pathlib import Path

import pytest
import yaml

from bau import tiktok
from bau.audit import AuditLog
from bau.platforms import PlatformRegistry

MB = 1024 * 1024
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class FakeTikTok(tiktok.Http):
    def __init__(self, status="PUBLISH_COMPLETE"):
        self.calls = []
        self.final_status = status
        self.received = 0

    def request(self, method, url, headers, body=None, timeout=120):
        self.calls.append((method, url, headers, body))
        if url.endswith("/v2/oauth/token/"):
            return 200, json.dumps({"access_token": "new-at", "refresh_token": "new-rt",
                                    "expires_in": 86400, "refresh_expires_in": 31536000,
                                    "open_id": "o1", "scope": tiktok.SCOPES}).encode()
        if url.endswith("/creator_info/query/"):
            return 200, json.dumps({"data": {
                "creator_nickname": "BAU Studio", "creator_username": "baustudio",
                "privacy_level_options": ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS",
                                          "SELF_ONLY"],
                "comment_disabled": False, "duet_disabled": True, "stitch_disabled": False,
                "max_video_post_duration_sec": 600}, "error": {"code": "ok"}}).encode()
        if url.endswith("/video/init/"):
            return 200, json.dumps({"data": {"publish_id": "p_1",
                                             "upload_url": "https://upload.example/u"},
                                    "error": {"code": "ok"}}).encode()
        if method == "PUT":
            self.received += len(body)
            total = int(headers["Content-Range"].rsplit("/", 1)[1])
            return (201 if self.received == total else 206), b""
        if url.endswith("/status/fetch/"):
            return 200, json.dumps({"data": {"status": self.final_status},
                                    "error": {"code": "ok"}}).encode()
        return 404, b"{}"

    def json_of(self, suffix):
        return [json.loads(b) for m, u, h, b in self.calls if u.endswith(suffix)]


def setup(home, size=1000, ai_prov=True):
    PlatformRegistry(home).upsert(yaml.safe_load((EXAMPLES / "platform-tiktok.yaml")
                                                 .read_text()) | {"last_verified":
                                                                  str(__import__(
                                                                      "datetime").date
                                                                      .today())})
    arts = home / "artifacts" / "videos"
    arts.mkdir(parents=True)
    video = arts / "clip.mp4"
    video.write_bytes(b"v" * size)
    if ai_prov:
        (arts / "clip.mp4.provenance.json").write_text(json.dumps({
            "artifact_id": "a1", "media_type": "video", "ai_generated": True,
            "ai_assisted": False, "human_authored": False, "human_modified": True,
            "model_id": "m", "visible_disclosure_text": "AI-GENERATED VIDEO",
            "artifact_sha256": hashlib.sha256(video.read_bytes()).hexdigest()}))
    client = tiktok.TikTokClient(home, http=FakeTikTok(), creds=("ck", "cs"))
    client.tokens.save({"access_token": "at", "refresh_token": "rt", "expires_in": 86400,
                        "refresh_expires_in": 31536000})
    q = tiktok.TikTokQueue(home, AuditLog(home / "audit" / "chain.jsonl", key=b""))
    return video, client, q


def answers(*seq):
    it = iter(seq)
    return lambda prompt: next(it)


def test_chunk_plan_and_pkce():
    assert tiktok.chunk_plan(3 * MB) == (3 * MB, 1)               # < 5 MB: one chunk
    assert tiktok.chunk_plan(8 * MB) == (8 * MB, 1)
    assert tiktok.chunk_plan(25 * MB + 7) == (10 * MB, 2)          # remainder in the last
    with pytest.raises(tiktok.TikTokError):
        tiktok.chunk_plan(0)
    v, c = tiktok.pkce_pair()
    assert 43 <= len(v) <= 128 and c == hashlib.sha256(v.encode()).hexdigest()


def test_review_click_posts_with_tiktok_requirements(tmp_path, engine):
    video, client, q = setup(tmp_path)
    item = q.add(video, "New lyric video out now #music", "human:owner", engine=engine)
    assert item.checks["ok"], item.checks
    assert item.checks["gate"] == "PASS_WITH_REVIEW" and item.is_aigc
    said = []
    # invalid privacy input is re-asked: there is no default
    done = tiktok.review(q, client, "human:owner",
                         answers("", "9", "1", "y", "y"), said.append)
    assert done[0].status == "POSTED" and done[0].publish_id == "p_1"
    init = client.http.json_of("/v2/post/publish/video/init/")[0]
    assert init["post_info"]["privacy_level"] == "PUBLIC_TO_EVERYONE"
    assert init["post_info"]["is_aigc"] is True
    assert init["post_info"]["brand_organic_toggle"] is True
    assert init["post_info"]["disable_duet"] is True                 # creator setting kept
    assert init["source_info"] == {"source": "FILE_UPLOAD", "video_size": 1000,
                                   "chunk_size": 1000, "total_chunk_count": 1}
    put = [c for c in client.http.calls if c[0] == "PUT"][0]
    assert put[2]["Content-Range"] == "bytes 0-999/1000"
    assert any("BAU Studio (@baustudio)" in s for s in said)
    assert any("Music Usage Confirmation" in s for s in said)
    with pytest.raises(tiktok.TikTokError, match="only once"):
        q.post(done[0], client, "human:owner", "SELF_ONLY", {}, {})
    events = [r["event"] for r in AuditLog(tmp_path / "audit" / "chain.jsonl",
                                           key=b"").records()]
    assert "approval.granted" in events and "tiktok.published" in events


def test_nobody_but_a_human_posts(tmp_path, engine):
    video, client, q = setup(tmp_path)
    item = q.add(video, "clip", "human:owner", engine=engine)
    with pytest.raises(PermissionError):
        q.post(item, client, "agent:writer", "SELF_ONLY", {}, client.creator_info())
    with pytest.raises(PermissionError):
        tiktok.review(q, client, "governor", answers())
    assert not client.http.json_of("/video/init/")


def test_blocked_items_never_post(tmp_path, engine):
    video, client, q = setup(tmp_path)
    bad = q.add(video, "Guaranteed results, risk-free!", "human:owner", engine=engine)
    assert not bad.checks["ok"] and "claims" in bad.checks["problems"][0]
    off = q.add(video, "fine caption", "human:owner", is_aigc=False, engine=engine)
    assert off.is_aigc and not off.checks["ok"]                        # AI provenance wins
    outside = tmp_path / "elsewhere.mp4"
    outside.write_bytes(b"x")
    with pytest.raises(tiktok.TikTokError):
        q.add(outside, "x", "human:owner", engine=engine)
    tiktok.review(q, client, "human:owner", answers("r", "r"), lambda s: None)
    assert not client.http.json_of("/video/init/")
    assert all(i.status == "REJECTED" for i in q.items())


def test_edited_video_after_check_is_refused(tmp_path, engine):
    video, client, q = setup(tmp_path, ai_prov=False)
    ai_no_record = q.add(video, "x", "human:owner", engine=engine)
    assert ai_no_record.checks["gate"] == "BLOCKED"            # AI video needs provenance
    item = q.add(video, "behind the scenes", "human:owner", is_aigc=False, engine=engine)
    assert item.checks["ok"] and not item.is_aigc             # human-made, owner says so
    video.write_bytes(b"changed")
    with pytest.raises(tiktok.TikTokError, match="changed"):
        q.post(item, client, "human:owner", "SELF_ONLY", {}, client.creator_info())


def test_draft_mode_and_chunked_upload(tmp_path, engine):
    video, client, q = setup(tmp_path, size=12 * MB)
    client.http.final_status = "SEND_TO_USER_INBOX"
    q.add(video, "draft me", "human:owner", engine=engine)
    done = tiktok.review(q, client, "human:owner", answers("y"), lambda s: None, draft=True)
    assert done[0].status == "DRAFTED"
    init = client.http.json_of("/v2/post/publish/inbox/video/init/")[0]
    assert "post_info" not in init and init["source_info"]["total_chunk_count"] == 1
    assert client.http.received == 12 * MB


def test_token_refresh_and_secret_file_mode(tmp_path):
    client = tiktok.TikTokClient(tmp_path, http=FakeTikTok(), creds=("ck", "cs"))
    client.tokens.save({"access_token": "old", "refresh_token": "rt", "expires_in": 0,
                        "refresh_expires_in": 31536000})
    assert client.access_token() == "new-at"
    assert client.tokens.load()["refresh_token"] == "new-rt"        # rotated token kept
    assert oct(client.tokens.path.stat().st_mode & 0o777) == "0o600"
    form = client.http.calls[0][3].decode()
    assert "grant_type=refresh_token" in form
    rec = client.tokens.load()
    rec["refresh_expires_at"] = time.time() - 1
    rec["access_expires_at"] = 0
    client.tokens.path.write_text(json.dumps(rec))
    with pytest.raises(tiktok.TikTokError, match="login"):
        client.access_token()


def test_missing_platform_record_blocks(tmp_path, engine):
    video, client, q = setup(tmp_path)
    shutil.rmtree(tmp_path / "compliance")
    item = q.add(video, "clip", "human:owner", engine=engine)
    assert not item.checks["ok"] and any("policy record" in p for p in item.checks["problems"])


def test_login_round_trip_with_pkce_and_state(tmp_path):
    import socket
    import threading
    import urllib.parse
    import urllib.request
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    client = tiktok.TikTokClient(tmp_path, http=FakeTikTok(), creds=("ck", "cs"))
    seen = {}

    def browser(url):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        seen.update(q)
        cb = f"{q['redirect_uri']}?code=abc&state={q['state']}"
        threading.Timer(0.2, lambda: urllib.request.urlopen(cb).read()).start()

    tok = tiktok.login(client, port=port, open_browser=browser, timeout=10)
    assert tok["access_token"] == "new-at"
    assert seen["code_challenge_method"] == "S256" and len(seen["code_challenge"]) == 64
    assert seen["redirect_uri"] == f"http://127.0.0.1:{port}/callback/"
    assert "video.publish" in seen["scope"]
    form = dict(urllib.parse.parse_qsl(client.http.calls[-1][3].decode()))
    assert form["grant_type"] == "authorization_code" and form["code"] == "abc"
    assert hashlib.sha256(form["code_verifier"].encode()).hexdigest() == seen["code_challenge"]


def test_login_rejects_forged_state(tmp_path):
    import socket
    import threading
    import urllib.parse
    import urllib.request
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    client = tiktok.TikTokClient(tmp_path, http=FakeTikTok(), creds=("ck", "cs"))

    def browser(url):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        threading.Timer(0.2, lambda: urllib.request.urlopen(
            f"{q['redirect_uri']}?code=abc&state=forged").read()).start()

    with pytest.raises(tiktok.TikTokError, match="state"):
        tiktok.login(client, port=port, open_browser=browser, timeout=10)
    assert client.tokens.load() is None
