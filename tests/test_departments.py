"""The departments at work (the owner, 2026-11-20: the women "don't move or get to work";
"everybody has connections to things so they can work"): business tools the agents read,
finance and marketing agents, daily standing work, shifts whenever work waits, and the cards
that ask the owner to approve a worker and to file delivered work."""

import datetime as dt
import json

import pytest

from bau import agentfolders as AF
from bau import departments as D
from bau import workstation as W


def test_the_business_tools_read_the_real_records_and_never_project(tmp_path, monkeypatch):
    from bau.gateway import CallRequest
    from bau.runtime import build_gateway
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    eco = tmp_path / "economics"
    eco.mkdir()
    now = dt.datetime.now(dt.UTC)
    rows = [{"ts": now.isoformat(), "gross_usd": 10.0, "platform_fee": 2.0},
            {"ts": (now - dt.timedelta(days=10)).isoformat(), "gross_usd": 5.0,
             "platform_fee": 1.0},
            {"ts": now.isoformat(), "gross_usd": 3.0, "platform_fee": -0.6, "refund": True}]
    (eco / "revenue.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    gw = build_gateway(tmp_path)
    money = gw.invoke(CallRequest("agent:finance", "data.money", {}))
    assert money["today"]["received_usd"] == round(8.0 - 2.4, 2)        # refund counted
    assert money["last_30_days"]["received_usd"] == round(8.0 - 2.4 + 4.0, 2)
    assert money["today"]["refunds"] == 1 and "projected" in money["note"]
    fv = gw.invoke(CallRequest("agent:finance", "data.fanvue", {}))
    assert fv["posted"] == 0 and fv["fan_chat"]["waiting"] == 0


@pytest.mark.parametrize("name", ["finance", "marketer"])
def test_the_new_agents_are_valid_read_and_draft_only(name):
    a = AF.load(name, None)
    assert AF.problems(a) == []
    assert set(a.tools) <= {"data.money", "data.fanvue", "memory.search",
                            "memory.brain", "search.web", "artifact.write_draft"}


def test_every_standing_objective_passes_the_productivity_manager():
    for d in D.standing():
        assert not W.EXTERNAL.search(d["objective"]), d
        assert d["kind"] in W.LOW_RISK and d["role"] in AF.names(None)


def test_standing_work_only_for_approved_agents_once_a_day(tmp_path):
    assert D.due(tmp_path) == []                                     # nobody approved
    AF.approve("finance", "human:owner", tmp_path)
    made = D.due(tmp_path)
    assert [t["role"] for t in made] == ["finance"] and made[0]["status"] == "approved"
    assert D.due(tmp_path) == []                                     # one at a time
    st = W._load(tmp_path)
    st["tasks"][0]["status"] = "done"
    W._save(tmp_path, st)
    assert D.due(tmp_path) == []                                     # not again today
    later = dt.datetime.now(dt.UTC) + dt.timedelta(hours=25)
    assert [t["role"] for t in D.due(tmp_path, now=later)] == ["finance"]


def test_the_world_puts_finance_and_marketing_in_their_rooms():
    from bau.world import DESK
    assert DESK["finance"] == "finance" and DESK["marketer"] == "market"


def test_the_owner_approves_a_worker_and_files_delivered_work_on_cards(tmp_path):
    from bau.assistant import Assistant
    j = Assistant(tmp_path)
    cards = {j.pending[p["id"]].args.get("agent"): p for p in j.setup_waiting()
             if p["tool"] == "agent_approve"}
    assert {"finance", "marketer", "researcher", "producer"} <= set(cards)
    assert not cards["finance"]["voice"]                              # a click, never voice
    with pytest.raises(PermissionError):
        j.confirm(cards["finance"]["id"], True, "jarvis")
    assert j.confirm(cards["finance"]["id"], True, "human:owner")["done"]
    assert AF.approval(AF.load("finance", tmp_path), tmp_path) == "approved"
    j.confirm(cards["marketer"]["id"], False, "human:owner")          # Not now: asked later
    again = [p for p in j.setup_waiting() if p["tool"] == "agent_approve"]
    assert all(j.pending[p["id"]].args["agent"] != "marketer" for p in again)
    # a department delivers: its work pops up once, Accept files it
    t = W.assign(tmp_path, "finance", "Write today's earnings report", "human:owner")
    st = W._load(tmp_path)
    st["tasks"][-1].update(status="review", result="1 fact(s) no tool result backs: x",
                           report="Received today: $0.00.")
    W._save(tmp_path, st)
    work = [p for p in j.setup_waiting() if p["tool"] == "work_review"]
    assert len(work) == 1 and "Received today: $0.00." in work[0]["summary"]
    assert "Not checked" in work[0]["summary"]                      # said plainly
    assert j.confirm(work[0]["id"], True, "human:owner")["done"]
    assert W._load(tmp_path)["tasks"][-1]["seen"]["kept"] is True
    assert not [p for p in j.setup_waiting() if p["tool"] == "work_review"]
    assert t["role"] == "finance"
