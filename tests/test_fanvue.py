"""Fanvue (src/bau/fanvue.py): a picture drawn here and its caption are queued; the owner's
Accept on the card, with the audience they pick (no default), uploads and posts it; Fanvue's
earnings come into the ledger once each. Fake Fanvue only: no network, no keys."""

import base64
import hashlib
import json
import urllib.parse

import pytest

from bau import fanvue as F
from bau.economics import Ledger, metrics


class FakeFanvue:
    """Answers like api.fanvue.com and auth.fanvue.com (paths from the v1 reference)."""

    def __init__(self, earnings=None, media_status=("processing", "ready")):
        self.calls, self.puts = [], []
        self.earnings_pages = earnings or [{"data": [], "nextCursor": None}]
        self.media_status = list(media_status)
        self.refresh = 0

    def request(self, method, url, headers, body=None, timeout=120):
        self.calls.append((method, url, headers, body))
        path = urllib.parse.urlsplit(url).path
        if url == F.TOKEN_URL:
            form = dict(urllib.parse.parse_qsl(body.decode()))
            self.refresh += form["grant_type"] == "refresh_token"
            return 200, json.dumps({"access_token": f"at{self.refresh}",
                                    "refresh_token": f"rt{self.refresh}",
                                    "expires_in": 3600, "scope": F.SCOPES}).encode()
        if path == "/v1/users/me":
            return 200, json.dumps({"uuid": "me-1", "handle": "aria", "displayName": "Aria",
                                    "isCreator": True}).encode()
        if path == "/v1/media/uploads" and method == "POST":
            return 200, json.dumps({"mediaUuid": "m-1", "uploadId": "u-1", "partSize": 4,
                                    "totalParts": 2}).encode()
        if path.endswith("/parts/urls"):
            return 200, json.dumps({"parts": [{"partNumber": 2, "url": "https://s3/p2"},
                                              {"partNumber": 1, "url": "https://s3/p1"}]}
                                   ).encode()
        if path == "/v1/media/uploads/u-1":
            return 200, b'{"status": "processing"}'
        if path == "/v1/media/m-1":
            return 200, json.dumps({"uuid": "m-1", "status": self.media_status.pop(0)}).encode()
        if path == "/v1/posts":
            return 201, json.dumps({"uuid": "post-1", "publishedAt": "2026-11-03T12:00:00Z"}
                                   ).encode()
        if path == "/v1/insights/earnings":
            return 200, json.dumps(self.earnings_pages.pop(0)).encode()
        return 404, b'{"error": "not found"}'

    def put_part(self, url, body):
        self.puts.append((url, body))
        return 200, f'"etag-{url[-1]}"'


def client(tmp_path, fake, token=True):
    c = F.FanvueClient(tmp_path, http=fake, creds=("cid", "csecret"), sleep=lambda s: None)
    if token:
        c.tokens.save({"access_token": "at0", "refresh_token": "rt0", "expires_in": 3600})
    return c


def picture(home, name="a.png", data=b"PNGDATA!", passed=True):
    media = home / "artifacts" / "media"
    media.mkdir(parents=True, exist_ok=True)
    (media / name).write_bytes(data)
    prov = {"ai_generated": True, "file_sha256": hashlib.sha256(data).hexdigest(),
            "age_check": {"passed": passed}}
    (media / f"{name}.provenance.json").write_text(json.dumps(prov))
    return name


# ------------------------------------------------------------------ login
def test_login_is_pkce_s256_with_the_documented_scopes_and_basic_client_auth(tmp_path):
    verifier, challenge = F.pkce_pair()
    assert challenge == base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    fake = FakeFanvue()
    c = client(tmp_path, fake, token=False)
    url = c.authorize_url("http://127.0.0.1:3456/callback", "s" * 64, challenge)
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    assert url.startswith(F.AUTH_URL) and q["code_challenge_method"] == "S256"
    assert {"openid", "offline_access", "write:post", "write:media", "read:insights"} <= set(
        q["scope"].split(" "))
    c.exchange("code1", "http://127.0.0.1:3456/callback", verifier)
    _, _, headers, body = fake.calls[-1]
    assert headers["Authorization"] == "Basic " + base64.b64encode(b"cid:csecret").decode()
    assert "code_verifier=" in body.decode()
    assert (tmp_path / "secrets" / "fanvue.json").stat().st_mode & 0o777 == 0o600


def test_refresh_tokens_rotate_and_the_new_one_is_kept(tmp_path):
    fake = FakeFanvue()
    c = client(tmp_path, fake)
    tok = c.tokens.load()
    tok["access_expires_at"] = 0
    c.tokens.path.write_text(json.dumps(tok))
    c.me()
    assert fake.refresh == 1 and c.tokens.load()["refresh_token"] == "rt1"
    api = [h for _, u, h, _ in fake.calls if "api.fanvue.com" in u]
    assert api[-1]["X-Fanvue-API-Version"] == "2025-06-26"
    assert api[-1]["Authorization"] == "Bearer at1"


# ------------------------------------------------------------------ queue
def test_queue_adds_the_ai_label_and_refuses_what_must_not_go(tmp_path):
    q = F.Queue(tmp_path)
    item = q.add(picture(tmp_path), "Evening in, new set", 1, "human:owner")
    assert item["caption"].endswith(F.AI_LABEL) and item["status"] == "QUEUED"
    with pytest.raises(ValueError, match="minors"):
        q.add(picture(tmp_path), "cute schoolgirl look", 0, "human:owner")
    with pytest.raises(ValueError, match="levels 0 and 1"):
        q.add(picture(tmp_path), "x", 2, "human:owner")
    with pytest.raises(ValueError, match="age check"):
        q.add(picture(tmp_path, "b.png", passed=False), "x", 0, "human:owner")
    with pytest.raises(ValueError, match="artifacts/media"):
        q.add("../secrets/fanvue.json", "x", 0, "human:owner")


def test_accept_uploads_then_posts_once_with_the_owners_audience(tmp_path):
    fake = FakeFanvue()
    q = F.Queue(tmp_path)
    item = q.add(picture(tmp_path), "Evening in", 1, "human:owner")
    with pytest.raises(PermissionError):
        q.post(item, client(tmp_path, fake), "jarvis", "subscribers")
    with pytest.raises(F.FanvueError, match="audience"):
        q.post(item, client(tmp_path, fake), "human:owner", "")
    done = q.post(q.get(item["item_id"]), client(tmp_path, fake), "human:owner", "subscribers")
    assert done["status"] == "POSTED" and done["result"]["post_uuid"] == "post-1"
    # parts PUT in order, raw bytes, no Authorization; ETags handed back
    assert fake.puts == [("https://s3/p1", b"PNGD"), ("https://s3/p2", b"ATA!")]
    urls = [u for _, u, _, _ in fake.calls]
    assert any("/v1/creators/me-1/media/uploads/u-1/parts/urls?from=1&to=2" in u for u in urls)
    patch = next(json.loads(b) for m, u, _, b in fake.calls if m == "PATCH")
    assert patch == {"parts": [{"PartNumber": 1, "ETag": '"etag-1"'},
                               {"PartNumber": 2, "ETag": '"etag-2"'}]}
    post = next(json.loads(b) for m, u, _, b in fake.calls if u.endswith("/v1/posts"))
    assert post == {"text": item["caption"], "audience": "subscribers", "mediaUuids": ["m-1"]}
    with pytest.raises(F.FanvueError, match="only once"):
        q.post(q.get(item["item_id"]), client(tmp_path, fake), "human:owner", "subscribers")


def test_a_changed_picture_or_a_hold_stops_the_post(tmp_path):
    from bau.governor import Governor
    q = F.Queue(tmp_path)
    item = q.add(picture(tmp_path), "Evening in", 0, "human:owner")
    (tmp_path / "artifacts" / "media" / "a.png").write_bytes(b"other")
    with pytest.raises(F.FanvueError, match="changed"):
        q.post(item, client(tmp_path, FakeFanvue()), "human:owner", "subscribers")
    item2 = q.add(picture(tmp_path, "c.png"), "Evening in", 0, "human:owner")
    Governor(tmp_path).hold("test", "human:owner")
    with pytest.raises(F.FanvueError, match="HOLD"):
        q.post(item2, client(tmp_path, FakeFanvue()), "human:owner", "subscribers")


def test_jarvis_queues_and_stages_the_card_and_only_the_owners_accept_posts(tmp_path):
    from bau.assistant import Assistant
    fake = FakeFanvue()
    j = Assistant(tmp_path, clients={"fanvue": client(tmp_path, fake)})
    name = picture(tmp_path)
    out, _ = j._run_tool("fanvue_queue", {"picture": name, "caption": "Evening in",
                                          "level": 1})
    out, _ = j._run_tool("post_video", {"platform": "fanvue", "item_id": out["queued"],
                                        "audience": "subscribers"})      # model can't choose
    p = j.pending[out["pending_id"]]
    assert "audience" not in p.args and p.preview.endswith("a.png")
    assert [o[0] for o in p.form["fields"][0]["options"]] == list(F.AUDIENCES)
    assert not any(u.endswith("/v1/posts") for _, u, _, _ in fake.calls)   # nothing yet
    assert j.confirm(p.id, True, "human:owner")["retry"]                    # must choose
    done = j.confirm(p.id, True, "human:owner", {"audience": "followers-and-subscribers"})
    assert done["done"] and done["result"]["status"] == "POSTED"


# ------------------------------------------------------------------ earnings
def test_earnings_come_into_the_ledger_once_in_dollars_with_refunds(tmp_path):
    rows = [{"date": "2026-11-02T10:00:00Z", "gross": 999, "net": 799, "source": "subscription",
             "transactionOrderId": "t1"},
            {"date": "2026-11-02T11:00:00Z", "gross": 1499, "net": 1199, "source": "post",
             "transactionOrderId": "t2"},
            {"date": "2026-11-02T12:00:00Z", "gross": -1499, "net": -1199, "source": "refund",
             "transactionOrderId": "t3"}]
    fake = FakeFanvue(earnings=[{"data": rows[:2], "nextCursor": "c2"},
                                {"data": rows[2:], "nextCursor": None},
                                {"data": rows, "nextCursor": None}])
    c = client(tmp_path, fake)
    out = F.sync_earnings(tmp_path, c)
    assert out["new_rows"] == 3 and out["net_usd"] == 7.99
    assert F.sync_earnings(tmp_path, c)["new_rows"] == 0           # never counted twice
    m = metrics(Ledger(tmp_path))
    assert round(m["revenue"], 2) == 9.99 and round(m["fees"], 2) == 2.0   # 7.99 kept


def test_the_money_tool_reads_fanvue_first_once_connected(tmp_path, monkeypatch):
    from bau.assistant import Assistant
    fake = FakeFanvue(earnings=[{"data": [{"date": "2026-11-02T10:00:00Z", "gross": 999,
                                           "net": 799, "source": "subscription",
                                           "transactionOrderId": "t1"}],
                                 "nextCursor": None}])
    c = client(tmp_path, fake)                   # the token on disk = connected
    monkeypatch.setattr(F, "FanvueClient", lambda home: c)
    out = Assistant(tmp_path).t_money()
    assert out["fanvue"]["new_rows"] == 1 and round(out["revenue"], 2) == 9.99


# ------------------------------------------------------------------ setup card
def test_connect_card_shows_only_with_the_apps_keys_and_goes_once_connected(tmp_path,
                                                                            monkeypatch):
    from bau import setup_steps as S
    monkeypatch.setattr(F, "app_credentials", lambda: (_ for _ in ()).throw(F.FanvueError()))
    assert S._done("fanvue", tmp_path, lambda w: None) is None
    monkeypatch.setattr(F, "app_credentials", lambda: ("cid", "secret"))
    assert S._done("fanvue", tmp_path, lambda w: None) is False
    assert S._command("fanvue", tmp_path) == "bau fanvue login"
    client(tmp_path, FakeFanvue())
    assert S._done("fanvue", tmp_path, lambda w: None) is True


def test_the_card_shows_the_picture_as_a_picture(tmp_path):
    import threading
    import urllib.request

    from bau.assistant import Assistant
    from bau.ui.jarvis_server import Voice, serve
    j = Assistant(tmp_path, clients={"fanvue": client(tmp_path, FakeFanvue())})
    out, _ = j._run_tool("fanvue_queue", {"picture": picture(tmp_path), "caption": "Hi",
                                          "level": 0})
    pid = j._run_tool("post_video", {"platform": "fanvue", "item_id": out["queued"]}
                      )[0]["pending_id"]
    srv, key = serve(j, Voice(tmp_path), 0, key="k123")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/api/preview/"
                                     f"{pid}", headers={"X-Jarvis-Key": key})
        with urllib.request.urlopen(req) as r:
            assert r.headers["Content-Type"] == "image/png" and r.read() == b"PNGDATA!"
    finally:
        srv.shutdown()
