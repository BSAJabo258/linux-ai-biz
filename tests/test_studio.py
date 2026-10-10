"""Video studio: Higgsfield clips under the owner's budget, written before the code.

Nothing is spent until the owner sets a budget and approves the provider; every clip is
priced first, refused when over budget, and only runs on the owner's Confirm. Completed
clips are downloaded with a provenance record and their cost lands in the ledger the
Governor watches.
"""

import io
import json
import urllib.error

import pytest

from bau.audit import AuditLog
from bau.economics import Ledger
from bau.media.higgsfield import Higgsfield, HiggsfieldBusy, HiggsfieldError, request_body
from bau.runtime import seed_registry

KEY_ID, SECRET = "kid-123", "sec-456"
VIDEO = b"\x00\x00\x00\x18ftypmp42" + b"v" * 2000


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeAPI:
    """Stands in for api.higgsfield.ai as documented on 2026-10-10."""

    def __init__(self, usd=0.84, finish="completed", busy=False):
        self.usd, self.finish, self.busy = usd, finish, busy
        self.calls, self.polls = [], 0

    def __call__(self, req, timeout=0):
        url = req.full_url
        self.calls.append((req.get_method(), url, dict(req.header_items()),
                           json.loads(req.data) if req.data else None))
        if url.startswith("https://cdn.example.com/"):
            return Resp(VIDEO)
        if "/estimate/" in url:
            return Resp(json.dumps({"credits": 21, "usd": self.usd}).encode())
        if url.endswith("/status"):
            self.polls += 1
            if self.polls < 2:
                return Resp(json.dumps({"status": "in_progress", "request_id": "r1"}).encode())
            body = {"status": self.finish, "request_id": "r1"}
            if self.finish == "completed":
                body["video"] = {"url": "https://cdn.example.com/clip.mp4"}
            return Resp(json.dumps(body).encode())
        if self.busy:
            raise urllib.error.HTTPError(url, 400, "Bad Request", {}, io.BytesIO(
                b'{"detail": "Maximum number of concurrent requests (4) has been reached"}'))
        return Resp(json.dumps({
            "status": "queued", "request_id": "r1",
            "status_url": "https://api.higgsfield.ai/requests/r1/status",
            "cancel_url": "https://api.higgsfield.ai/requests/r1/cancel"}).encode())

    def submits(self):
        return [c for c in self.calls if c[0] == "POST" and "/estimate/" not in c[1]]


def client(api):
    return Higgsfield(KEY_ID, SECRET, opener=api, sleep=lambda s: None)


# ------------------------------------------------------------------ the API client

def test_client_prices_submits_and_polls_as_documented():
    api = FakeAPI()
    hf = client(api)
    body = request_body("kling-3-pro", "A paper boat on a pond at dawn", 5, "9:16", "off")
    assert hf.estimate("kling-3-pro", body) == {"credits": 21, "usd": 0.84}
    method, url, headers, sent = api.calls[0]
    assert url == "https://api.higgsfield.ai/estimate/kling-video/v3.0/pro/text-to-video"
    assert headers["Authorization"] == f"Key {KEY_ID}:{SECRET}"
    r = hf.submit("kling-3-pro", body, "idem-1")
    assert r["request_id"] == "r1" and api.calls[1][2]["Idempotency-key"] == "idem-1"
    assert api.calls[1][3] == {"prompt": "A paper boat on a pond at dawn", "duration": 5,
                               "aspect_ratio": "9:16", "sound": "off"}
    done = hf.wait(r)
    assert done["video"]["url"] == "https://cdn.example.com/clip.mp4" and api.polls == 2


def test_request_body_is_checked_before_anything_is_sent():
    with pytest.raises(HiggsfieldError, match="model"):
        request_body("sora-9", "x", 5, "16:9", "on")
    with pytest.raises(HiggsfieldError, match="3 to 15"):
        request_body("kling-3-pro", "x", 30, "16:9", "on")
    with pytest.raises(HiggsfieldError, match="aspect"):
        request_body("kling-3-pro", "x", 5, "4:3", "on")
    with pytest.raises(HiggsfieldError, match="prompt"):
        request_body("kling-3-pro", " ", 5, "16:9", "on")
    with pytest.raises(HiggsfieldError, match="2500"):
        request_body("kling-3-pro", "x" * 2501, 5, "16:9", "on")


def test_busy_moderated_and_failed_are_plain_errors_with_no_key_in_them():
    with pytest.raises(HiggsfieldBusy, match="concurrent"):
        client(FakeAPI(busy=True)).submit("kling-3-pro", request_body(
            "kling-3-pro", "x", 5, "16:9", "on"), "i")
    for finish in ("nsfw", "failed", "canceled"):
        api = FakeAPI(finish=finish)
        hf = client(api)
        with pytest.raises(HiggsfieldError, match=finish) as e:
            hf.wait(hf.submit("kling-3-pro", request_body("kling-3-pro", "x", 5, "16:9",
                                                          "on"), "i"))
        assert SECRET not in str(e.value)


def test_downloads_only_from_https():
    hf = client(FakeAPI())
    with pytest.raises(HiggsfieldError, match="https"):
        hf.download("http://cdn.example.com/clip.mp4", None)


# ------------------------------------------------------------------ the studio (money)

@pytest.fixture
def studio(tmp_path, monkeypatch):
    from bau.studio import Studio
    seed_registry(tmp_path)
    monkeypatch.setenv("HIGGSFIELD_API_KEY_ID", KEY_ID)
    monkeypatch.setenv("HIGGSFIELD_API_KEY_SECRET", SECRET)
    api = FakeAPI()
    s = Studio(tmp_path, AuditLog(tmp_path / "audit" / "chain.jsonl", key=b""),
               client=client(api))
    return s, api, tmp_path


def approve_provider(home):
    import yaml
    p = home / "registry" / "capabilities.yaml"
    d = yaml.safe_load(p.read_text())
    d["provider"]["higgsfield"]["status"] = "APPROVED"
    p.write_text(yaml.safe_dump(d))


def test_nothing_is_spent_without_a_budget_and_an_approved_provider(studio):
    s, api, home = studio
    q = s.quote("A paper boat on a pond", "kling-3-pro", 5, "16:9", "off")
    assert not q["allowed"] and "budget" in q["why"]
    s.set_budget(monthly=20, per_clip=2, by="human:owner")
    q = s.quote("A paper boat on a pond", "kling-3-pro", 5, "16:9", "off")
    assert not q["allowed"] and "bau set-status provider higgsfield APPROVED" in q["why"]
    with pytest.raises(PermissionError):
        s.make("A paper boat on a pond", "kling-3-pro", 5, "16:9", "off", by="human:owner")
    assert api.submits() == []                                   # never sent
    with pytest.raises(PermissionError):
        s.set_budget(monthly=999, per_clip=99, by="agent:jarvis")


def test_a_clip_runs_only_for_the_owner_and_within_budget(studio):
    s, api, home = studio
    s.set_budget(monthly=20, per_clip=2, by="human:owner")
    approve_provider(home)
    q = s.quote("A paper boat on a pond", "kling-3-pro", 5, "16:9", "off")
    assert q["allowed"] and q["usd"] == 0.84 and q["left_this_month"] == 20
    with pytest.raises(PermissionError):
        s.make("A paper boat", "kling-3-pro", 5, "16:9", "off", by="agent:jarvis")
    api.usd = 2.5                                               # over the per-clip limit
    with pytest.raises(PermissionError, match="per-clip"):
        s.make("A paper boat", "kling-3-pro", 5, "16:9", "off", by="human:owner")
    assert api.submits() == []
    api.usd = 0.84
    job = s.make("A paper boat on a pond", "kling-3-pro", 5, "16:9", "off", by="human:owner")
    assert job["status"] == "submitted" and len(api.submits()) == 1
    assert s.refresh()[0]["status"] == "submitted"              # one look: still going
    clips = s.refresh()                                         # next look: done
    assert clips[0]["status"] == "completed"
    out = home / "studio" / "clips" / f"{job['id']}.mp4"
    assert out.read_bytes() == VIDEO
    prov = json.loads((out.parent / (out.name + ".provenance.json")).read_text())
    assert prov["ai_generated"] and prov["provider"] == "higgsfield"
    spent = [c for c in Ledger(home).costs if c.get("agent") == "studio"]
    assert len(spent) == 1 and spent[0]["usd"] == 0.84 and spent[0]["provider"] == "higgsfield"
    s.refresh()                                                 # never charged twice
    assert len([c for c in Ledger(home).costs if c.get("agent") == "studio"]) == 1
    text = (home / "audit" / "chain.jsonl").read_text() + (home / "studio" /
                                                           "jobs.jsonl").read_text()
    assert SECRET not in text and KEY_ID not in text


def test_monthly_budget_counts_what_is_already_spent(studio):
    s, api, home = studio
    s.set_budget(monthly=1.5, per_clip=2, by="human:owner")
    approve_provider(home)
    s.make("Clip one", "kling-3-pro", 5, "16:9", "off", by="human:owner")
    s.refresh()
    s.refresh()
    q = s.quote("Clip two", "kling-3-pro", 5, "16:9", "off")
    assert not q["allowed"] and "month" in q["why"]


def test_failed_or_moderated_clips_cost_nothing(studio):
    s, api, home = studio
    s.set_budget(monthly=20, per_clip=2, by="human:owner")
    approve_provider(home)
    api.finish = "nsfw"
    s.make("A paper boat", "kling-3-pro", 5, "16:9", "off", by="human:owner")
    s.refresh()
    clips = s.refresh()
    assert clips[0]["status"] == "nsfw" and "moderation" in clips[0]["note"]
    assert [c for c in Ledger(home).costs if c.get("agent") == "studio"] == []


def test_a_hold_stops_new_clips(studio):
    from bau.governor import Governor
    s, api, home = studio
    s.set_budget(monthly=20, per_clip=2, by="human:owner")
    approve_provider(home)
    Governor(home, audit=s.audit, systemctl="").hold("test", by="human:owner")
    with pytest.raises(PermissionError, match="HOLD"):
        s.make("A paper boat", "kling-3-pro", 5, "16:9", "off", by="human:owner")


# ------------------------------------------------------------------ Jarvis only stages it

def test_jarvis_can_only_put_a_clip_on_the_owners_screen(studio):
    from bau.assistant import Assistant
    s, api, home = studio
    s.set_budget(monthly=20, per_clip=2, by="human:owner")
    approve_provider(home)
    a = Assistant(home, None, {}, "human:owner", s.audit, clients={"higgsfield": s.client})
    assert a.tools["make_video"].kind == "confirm"
    out, err = a._run_tool("make_video", {"prompt": "A paper boat on a pond",
                                          "model": "kling-3-pro", "duration": 5,
                                          "aspect_ratio": "16:9", "sound": "off"})
    assert not err and api.submits() == []                      # nothing sent yet
    card = a.pending[out["pending_id"]]
    assert "$0.84" in card.summary and "left this month" in card.summary
    r = a.confirm(card.id, True, "human:owner")
    assert r["done"] and r["result"]["status"] == "submitted" and len(api.submits()) == 1


def test_cli_budget_needs_a_person_at_the_terminal(tmp_path, monkeypatch):
    from bau.cli import main
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert main(["video", "budget", "--monthly", "50", "--per-clip", "3"]) == 3


# ------------------------------------------------------------------ the Studio on screen

def test_studio_node_and_screen_endpoints(studio):
    import threading
    import urllib.request

    from bau.assistant import Assistant, Voice
    from bau.overview import overview
    from bau.ui.jarvis_server import serve
    s, api, home = studio
    a = Assistant(home, None, {}, "human:owner", s.audit, clients={"higgsfield": s.client})
    node = {n["id"]: n for n in overview(a)["nodes"]}["studio"]
    assert node["state"] == "idle" and "no video budget" in node["summary"]
    s.set_budget(monthly=20, per_clip=2, by="human:owner")
    approve_provider(home)
    srv, _ = serve(a, Voice(home), 0, key="k123")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"

    def call(path, body=None):
        h = {"X-Jarvis-Key": "k123"}
        data = None
        if body is not None:
            data, h["Content-Type"] = json.dumps(body).encode(), "application/json"
        with urllib.request.urlopen(urllib.request.Request(url + path, data=data,
                                                           headers=h)) as r:
            return r.status, r.read()
    try:
        code, raw = call("/api/studio/stage", {"prompt": "A paper boat", "model":
                                               "kling-3-pro", "duration": 5,
                                               "aspect_ratio": "16:9", "sound": "off"})
        staged = json.loads(raw)
        assert "$0.84" in staged["pending"][0]["summary"] and api.submits() == []
        code, raw = call("/api/confirm", {"id": staged["pending"][0]["id"], "approve": True})
        assert json.loads(raw)["result"]["status"] == "submitted"
        for _ in range(2):
            code, raw = call("/api/studio")
        d = json.loads(raw)
        clip = d["clips"][0]
        assert clip["status"] == "completed" and d["spent_this_month"] == 0.84
        code, raw = call(f"/api/studio/clip/{clip['id']}")
        assert raw == VIDEO
        node = {n["id"]: n for n in overview(a)["nodes"]}["studio"]
        assert node["state"] == "ok" and "$0.84" in node["summary"]
        try:
            call("/api/studio/clip/..%2F..%2Fetc")
            raise AssertionError("path escaped")
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        srv.shutdown()
