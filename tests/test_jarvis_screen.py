"""The Jarvis screen: live nodes around the core, episode buttons, owner-only checks."""

import json
import threading
import urllib.error
import urllib.request

import pytest
from test_workspace import BIBLE

from bau import workspace as W
from bau.assistant import Assistant, Voice
from bau.audit import AuditLog
from bau.models.providers import ScriptedProvider
from bau.overview import overview

MODEL = {"id": "test-model", "context": 32768}


def make(home, script=None):
    prov = ScriptedProvider(list(script)) if script is not None else None
    return Assistant(home, prov, MODEL if prov else {}, "human:owner",
                     AuditLog(home / "audit" / "chain.jsonl", key=b""))


def nodes(a):
    return {n["id"]: n for n in overview(a)["nodes"]}


def with_episode(home):
    ws = W.create("kids-channel", home=home)
    (ws / "_shared" / "series-bible.md").write_text(BIBLE)
    return ws, W.new_episode(ws, "Pip learns to share berries")


def test_fresh_system_shows_every_part_and_never_claims_unmeasured_green(tmp_path):
    n = nodes(make(tmp_path))
    for nid in ("chief", "producer", "publisher", "strategist", "researcher", "compliance",
                "finance", "watchdog", "models", "memory", "audit", "email", "youtube"):
        assert nid in n
    assert n["models"]["state"] == "bad" and "plain mode" in n["models"]["summary"]
    assert n["producer"]["state"] == "idle" and n["finance"]["state"] == "idle"
    assert all(n[c]["state"] == "off" for c in ("email", "drive", "calendar", "crm",
                                                "youtube", "tiktok"))
    assert n["audit"]["state"] == "ok"


def test_a_broken_source_shows_red_with_its_error(tmp_path):
    a = make(tmp_path)
    a.t_money = lambda: (_ for _ in ()).throw(OSError("ledger unreadable"))
    fin = nodes(a)["finance"]
    assert fin["state"] == "bad" and "ledger unreadable" in fin["summary"]


def test_episode_node_offers_draft_then_owner_check(tmp_path):
    a = make(tmp_path, ["# Pip shares\nLearning goal: sharing."])
    ws, ep = with_episode(tmp_path)
    prod = nodes(a)["producer"]
    assert prod["detail"]["episodes"][0]["next"] == {"action": "draft", "stage": "01"}
    out, err = a._run_tool("draft_stage", {"workspace": ws.name, "episode": ep.name})
    assert not err
    prod = nodes(a)["producer"]
    assert prod["state"] == "warn" and prod["detail"]["episodes"][0]["next"]["action"] == "check"
    card = a.stage_check(ws.name, ep.name, "01")
    assert "Pip shares" in card["summary"] and card["tool"] == "check_stage"
    assert not W.is_checked(W.contracts(ep)[0])                  # nothing until Confirm
    assert a.confirm(card["id"], True, "human:owner")["done"]
    assert W.is_checked(W.contracts(ep)[0])
    assert nodes(a)["producer"]["detail"]["episodes"][0]["next"]["stage"] == "02"


def test_the_model_can_never_check_a_stage(tmp_path):
    a = make(tmp_path, ["x"])
    ws, ep = with_episode(tmp_path)
    assert "check_stage" not in a.tools and "check_stage" not in [s.name for s in a.specs()]
    out, err = a._run_tool("check_stage", {"workspace": ws.name, "episode": ep.name,
                                           "stage": "01"})
    assert err and "unknown tool" in out["error"]
    with pytest.raises(W.WorkspaceError, match="not written yet"):
        a.stage_check(ws.name, ep.name, "01")
    a._run_tool("draft_stage", {"workspace": ws.name, "episode": ep.name})
    card = a.stage_check(ws.name, ep.name, "01")
    with pytest.raises(PermissionError):
        a.confirm(card["id"], True, "agent:jarvis")


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


def test_screen_endpoints_draft_and_stage_checks_behind_the_key(tmp_path):
    from bau.ui.jarvis_server import serve
    a = make(tmp_path, ["# Pip shares\nLearning goal: sharing."])
    ws, ep = with_episode(tmp_path)
    srv, _ = serve(a, Voice(tmp_path), 0, key="k123")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        assert call(url, "/api/overview", key="nope")[0] == 403
        code, o = call(url, "/api/overview")
        assert code == 200 and {n["id"] for n in o["nodes"]} >= {"producer", "models"}
        code, r = call(url, "/api/check", {"workspace": ws.name, "episode": ep.name,
                                          "stage": "01"})
        assert "not written yet" in r["error"]
        code, r = call(url, "/api/draft", {"workspace": ws.name, "episode": ep.name})
        assert code == 200 and not r["error"] and r["result"]["stage"] == "01_pitch"
        # The owner's check comes back with the draft: the page pops it up at once.
        assert r["pending"][0]["tool"] == "check_stage"
        assert r["pending"][0]["id"] == r["result"]["pending_id"]
        code, r = call(url, "/api/check", {"workspace": ws.name, "episode": ep.name,
                                          "stage": "01"})
        pid = r["pending"][0]["id"]
        code, r = call(url, "/api/confirm", {"id": pid, "approve": True})
        assert r["done"] and r["result"]["checked"] == "01_pitch"
    finally:
        srv.shutdown()


def test_owner_choices_are_big_buttons_with_nothing_preselected():
    from pathlib import Path
    page = (Path(__file__).resolve().parents[1] / "src" / "bau" / "ui" / "jarvis.html"
            ).read_text(encoding="utf-8")
    assert "<select" not in page and 'el("select")' not in page        # no fiddly drop-downs
    assert 'el("button", "opt", label)' in page and "picked = {}" in page
    assert "To confirm, first choose: " in page                      # says what's missing
    assert "queueConfirms(r.pending)" in page                        # drafts pop the check
