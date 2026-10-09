"""The full Jarvis screen: live activity, working panels, timeline, Mission Control inside,
and the page itself (keys for every button, accessibility, opt-in wake word and alerts).
Written before the code it tests."""

import json
import re
import threading
import urllib.error
import urllib.request
from importlib import resources

import pytest
from test_scout import REQ, FakeGitHub, item
from test_workspace import BIBLE

from bau import workspace as W
from bau.accessibility import lint_html
from bau.activity import Activity
from bau.assistant import Assistant, Voice
from bau.audit import AuditLog
from bau.models.providers import ScriptedProvider

MODEL = {"id": "test-model", "context": 32768}
PAGE = (resources.files("bau.ui") / "jarvis.html").read_text()


def make(home, script=None, **clients):
    prov = ScriptedProvider(list(script)) if script is not None else None
    return Assistant(home, prov, MODEL if prov else {}, "human:owner",
                     AuditLog(home / "audit" / "chain.jsonl", key=b""), clients=clients)


def with_episode(home):
    ws = W.create("kids-channel", home=home)
    (ws / "_shared" / "series-bible.md").write_text(BIBLE)
    return ws, W.new_episode(ws, "Pip learns to share berries")


@pytest.fixture
def server(tmp_path):
    from bau.ui.jarvis_server import serve
    made = {}

    def start(a):
        srv, _ = serve(a, Voice(tmp_path), 0, key="k123")
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        made["srv"] = srv
        return f"http://127.0.0.1:{srv.server_address[1]}"
    yield start
    if "srv" in made:
        made["srv"].shutdown()


def call(url, path, body=None, key="k123"):
    h = {"X-Jarvis-Key": key}
    data = None
    if body is not None:
        data, h["Content-Type"] = json.dumps(body).encode(), "application/json"
    try:
        with urllib.request.urlopen(urllib.request.Request(url + path, data=data,
                                                           headers=h)) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None


def settle(url, code, body):
    """Follow a slow answer's job until it is done (the page does the same)."""
    import time
    for _ in range(100):
        if code != 202:
            return code, body
        time.sleep(0.05)
        code, body = call(url, f"/api/job/{body['job']}")
    raise AssertionError("job never finished")


# ------------------------------------------------------------------ 1. work shows live

def test_activity_feed_orders_events_and_knows_what_is_busy():
    act = Activity(size=5)
    act.emit("scout", "start", "Searching GitHub")
    act.emit("producer", "start", "Drafting step 01")
    act.emit("scout", "progress", "Search 1 of 3: 4 found")
    act.emit("producer", "done", "Step 01 drafted")
    feed = act.since(0)
    assert [e["seq"] for e in feed["events"]] == [1, 2, 3, 4]
    assert feed["busy"] == {"scout": "Search 1 of 3: 4 found"}
    assert act.since(3)["events"][0]["text"] == "Step 01 drafted"
    for i in range(10):
        act.emit("chief", "progress", f"n{i}")
    assert len(act.since(0)["events"]) == 5                # ring buffer, never grows


def test_every_tool_run_shows_on_its_node(tmp_path):
    a = make(tmp_path, ["# Pip shares\nLearning goal: sharing."])
    ws, ep = with_episode(tmp_path)
    a._run_tool("draft_stage", {"workspace": ws.name, "episode": ep.name})
    a._run_tool("draft_stage", {"workspace": "nope", "episode": "x"})
    ev = [(e["node"], e["kind"]) for e in a.activity.since(0)["events"]]
    assert ev[:2] == [("producer", "start"), ("producer", "done")]
    assert ev[-1] == ("producer", "error") and a.activity.since(0)["busy"] == {}


def test_scout_reports_each_search_as_it_goes(tmp_path):
    from bau.scout import Scout
    seen = []
    src = FakeGitHub({"*": [item("acme/sim")]}, fail={"synthetic customer personas"})
    Scout(tmp_path, src).find(REQ, max_queries=3, progress=seen.append)
    assert seen[0].startswith("Search 1 of 3")
    assert any("failed" in s for s in seen) and seen[-1].startswith("Ranked")


def test_server_streams_activity_behind_the_key(tmp_path, server):
    a = make(tmp_path)
    url = server(a)
    a.activity.emit("scout", "start", "Searching GitHub")
    assert call(url, "/api/activity?since=0", key="nope")[0] == 403
    code, feed = call(url, "/api/activity?since=0")
    assert code == 200 and feed["busy"] == {"scout": "Searching GitHub"}
    code, feed = call(url, f"/api/activity?since={feed['seq']}")
    assert feed["events"] == []


# ------------------------------------------------------------------ 2. panels you work in

def test_scout_panel_searches_reports_and_inspects_from_the_screen(tmp_path, server):
    def cloner(url_, dest):
        dest.mkdir(parents=True)
        (dest / "LICENSE").write_text("MIT License\nPermission is hereby granted, free of "
                                      "charge")
        return "abc123"
    a = make(tmp_path, github=FakeGitHub({"*": [item("acme/sim")]}), git_clone=cloner)
    url = server(a)
    code, r = settle(url, *call(url, "/api/scout/find", {"request": REQ}))
    assert code == 200 and r["found"] == 1
    code, s = call(url, "/api/scout")
    assert s["candidates"][0]["repo"] == "acme/sim" and s["runs"][0]["request"] == REQ
    code, rep = call(url, "/api/scout/report")
    assert rep["markdown"].startswith("# Repo Scout")
    code, r = settle(url, *call(url, "/api/scout/inspect", {"repo": "acme/sim"}))
    assert r["sentinel"] == "ELIGIBLE_FOR_SANDBOX" and r["licence"]["detected"] == "MIT"
    events = [x["event"] for x in AuditLog(tmp_path / "audit" / "chain.jsonl").records()]
    assert "scout.run" in events and "scout.inspected" in events
    assert call(url, "/api/scout/inspect", {"repo": "../etc"})[1]["error"]


def test_models_panel_tests_a_model_but_never_approves_it(tmp_path, server, monkeypatch):
    import yaml

    from bau.models import bench
    from bau.registry import CapabilityRegistry
    from bau.runtime import seed_registry
    seed_registry(tmp_path)
    monkeypatch.setattr(bench, "benchmark", lambda rec, provider=None: {
        "reply_ok": True, "tool_calls": True, "latency_ms": 900})
    url = server(make(tmp_path))
    code, r = settle(url, *call(url, "/api/models/bench", {"model": "glm-4.7-flash-zai"}))
    assert code == 200 and r["reply_ok"] and "bau set-status" in r["next"]
    rec = CapabilityRegistry(tmp_path / "registry" / "capabilities.yaml").data["model"][
        "glm-4.7-flash-zai"]
    assert rec["status"] == "REGISTERED" and rec["benchmark"]["reply_ok"]
    assert "APPROVED" not in yaml.safe_dump(rec)
    assert call(url, "/api/models/bench", {"model": "no-such"})[1]["error"]


def test_producer_panel_reads_and_edits_a_draft_and_editing_voids_the_check(
        tmp_path, server):
    a = make(tmp_path, ["# Pip shares\nLearning goal: sharing."])
    ws, ep = with_episode(tmp_path)
    url = server(a)
    q = f"workspace={ws.name}&episode={ep.name}&stage=01"
    assert call(url, f"/api/ws/stage?{q}")[1]["error"]          # nothing drafted yet
    a._run_tool("draft_stage", {"workspace": ws.name, "episode": ep.name})
    code, st = call(url, f"/api/ws/stage?{q}")
    assert st["file"] == "pitch.md" and "Pip shares" in st["text"] and not st["checked"]
    W.check(ws, ep, "01", "human:owner")
    code, r = call(url, "/api/ws/stage", {"workspace": ws.name, "episode": ep.name,
                                          "stage": "01", "text": "# Pip shares\nEdited.\n"})
    assert r["saved"] == "pitch.md" and not r["checked"]          # edit voids the check
    assert (W.contracts(ep)[0].out_dir / "pitch.md").read_text() == "# Pip shares\nEdited.\n"
    events = [x["event"] for x in AuditLog(tmp_path / "audit" / "chain.jsonl").records()]
    assert "workspace.edited" in events
    for bad in ({"stage": "../../x"}, {"stage": "02"}, {"text": "x" * 210_000},
                {"workspace": "../.."}, {"workspace": "a/b"}, {"episode": "*"}):
        body = {"workspace": ws.name, "episode": ep.name, "stage": "01", "text": "y", **bad}
        assert call(url, "/api/ws/stage", body)[1]["error"]


def test_owner_writes_the_review_stage_on_screen(tmp_path, server):
    a = make(tmp_path)
    ws, ep = with_episode(tmp_path)
    for c in W.contracts(ep)[:5]:                                 # stages 01-05 done
        (c.out_dir / c.outputs[0]).write_text("Title: Pip\nDescription: d\nTags: t\n"
                                              if c.stage.startswith("05") else "# ok\n")
        W.check(ws, ep, c.stage[:2], "human:owner")
    url = server(a)
    code, r = call(url, "/api/ws/stage", {"workspace": ws.name, "episode": ep.name,
                                          "stage": "06", "text": "Watched it all. File: v.mp4"})
    assert r["saved"] == "review.md"


# ------------------------------------------------------------------ 3. Mission Control inside

def test_mission_control_data_is_on_the_jarvis_screen(tmp_path, server):
    url = server(make(tmp_path))
    code, d = call(url, "/api/mc/status")
    assert code == 200 and "overall" in d
    assert call(url, "/api/mc/regulations")[0] == 200
    assert call(url, "/api/mc/nope")[0] == 404
    assert call(url, "/api/mc/..%2Fstatus")[0] == 404


# ------------------------------------------------------------------ 4. timeline

def test_timeline_is_the_audit_chain_newest_first(tmp_path, server):
    a = make(tmp_path)
    for i in range(5):
        a.audit.append("test.event", "human:owner", {"n": i})
    url = server(a)
    code, t = call(url, "/api/timeline?limit=3")
    assert [x["seq"] for x in t["items"]] == [4, 3, 2] and t["intact"]   # seq starts at 0
    assert t["items"][0]["summary"] == "n 4" and len(t["items"][0]["hash"]) == 12
    code, t = call(url, "/api/timeline?limit=3&before=2")
    assert [x["seq"] for x in t["items"]] == [1, 0]


# ------------------------------------------------------------------ 5-7. the page itself

def static_buttons():
    body = PAGE.split("<script>")[0]
    return re.findall(r"<button\b[^>]*>", body)


def test_every_button_has_a_key_listed_in_the_help():
    btns = static_buttons()
    assert len(btns) >= 8
    help_box = PAGE[PAGE.index('id="help"'):]
    for b in btns:
        key = re.search(r'data-key="([^"]+)"', b)
        assert key, f"button without a keyboard shortcut: {b}"
        assert f"<kbd>{key.group(1)}</kbd>" in help_box, f"key {key.group(1)} not in help"


def test_page_passes_the_accessibility_lint():
    assert lint_html(PAGE) == []


def test_wake_word_and_alerts_are_off_until_the_owner_turns_them_on():
    assert re.search(r"let wakeOn = false\b", PAGE)
    perm = [m.start() for m in re.finditer(r"Notification\.requestPermission", PAGE)]
    assert perm, "alerts are offered"
    fn = PAGE.index("async function enableAlerts")
    assert all(fn < p < fn + 800 for p in perm)          # only asked from the owner's click


def test_light_theme_zoom_and_phone_ring_exist():
    assert '[data-theme="light"]' in PAGE and "prefers-color-scheme" in PAGE
    assert "function setZoom" in PAGE and "pinch" in PAGE
    assert "function layoutRing" in PAGE and "swipe" in PAGE
