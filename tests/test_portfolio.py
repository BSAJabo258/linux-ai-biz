"""The mission portfolio (Phase 2 of the Universal Automaton directive, 2026-11-11): several
missions active at once, each with its own objective, owner-set priority, budget and measured
goal, its profit computed only from real ledger rows. Finishing the work is not success: a
mission meets its goal only when the ledger says so. One store (jobs/missions.jsonl), no second
mission database."""

import datetime as dt
import sys

import pytest
from test_mission_run import agent, jarvis

from bau import jarvis as J
from bau.economics import Budgets, Ledger, pnl
from bau.jobs import JobStore

NOW = dt.datetime(2026, 11, 20, tzinfo=dt.UTC)


def three_missions(home):
    j = jarvis(home)
    ms = [j.plan(o, "research", {}) for o in ("find software buyers' problems",
                                               "plan a music release", "price a template pack")]
    J.set_mission(j, ms[0].mission_id, "human:owner", priority=1, budget_usd=5.0)
    J.set_mission(j, ms[1].mission_id, "human:owner", priority=3, budget_usd=0.0,
                  goal={"metric": "profit_usd", "at_least": 20.0, "by": "2026-12-31"})
    J.set_mission(j, ms[2].mission_id, "human:owner", priority=2,
                  goal={"metric": "revenue_usd", "at_least": 10.0})
    return j, [m.mission_id for m in ms]


def test_several_missions_stay_active_each_with_its_own_money(tmp_path):
    j, (soft, music, tmpl) = three_missions(tmp_path)
    led = Ledger(tmp_path)
    led.cost("model", 1.25, mission_id=soft, agent="researcher")
    led.sale(15.0, mission_id=tmpl, platform_fee=1.5, customer_ref="c1", new_customer=True)
    led.cost("marketing", 3.0, mission_id=tmpl)
    led.sale(20.0, factory="fanvue", platform_fee=4.0)          # no mission: unattributed
    led.cost("model", 0.5, mission_id="fr_abc")                  # a factory run's id
    p = J.portfolio(tmp_path, now=NOW)
    # Active first, by the owner's priority; the template pack met its $10 goal: not active.
    assert [m["mission_id"] for m in p["missions"]] == [music, soft, tmpl]
    by = {m["mission_id"]: m for m in p["missions"]}
    assert all(m["status"] == "READY" for m in by.values())
    assert p["active"] == 2 and by[tmpl]["goal"]["met"] and not by[tmpl]["active"]
    assert by[soft]["money"]["cost_usd"] == 1.25 and by[soft]["budget_left_usd"] == 3.75
    t = by[tmpl]["money"]
    assert t["kept_usd"] == 13.5 and t["profit_usd"] == 10.5 and t["fees_usd"] == 1.5
    assert t["customers"] == 1 and t["customer_acquisition_cost_usd"] == 3.0
    assert by[music]["money"]["profit_usd"] == 0 and by[music]["budget_left_usd"] == 0.0
    assert p["unattributed"]["kept_usd"] == 16.0                 # Fanvue, until linked
    assert p["unattributed"]["cost_usd"] == 0.5 and p["unattributed"]["ids"] == ["", "fr_abc"]
    assert p["totals"]["kept_usd"] == 29.5 and p["totals"]["cost_usd"] == 4.75
    assert p["one_store"].endswith("missions.jsonl")


def test_money_is_only_what_the_ledger_received(tmp_path):
    led = Ledger(tmp_path)
    led.sale(30.0, mission_id="m1", payment_fee=1.0, customer_ref="a")
    led.sale(30.0, mission_id="m1", payment_fee=-1.0, refund=True, customer_ref="a")
    led.sale(10.0, mission_id="m1", customer_ref="b")
    led.cost("api", 2.0, mission_id="m1")
    led.human_time(2.0, mission_id="m1")
    from bau.accounting import Books
    Books(tmp_path).record(kind="invoice", amount="500.00", currency="USD", date="2026-11-11",
                           counterparty_ref="cust-1", description="pending invoice",
                           evidence_ref="BAU-1", mission_id="m1")
    p = pnl(led, "m1")
    assert p["revenue_usd"] == 40.0 and p["refunds_usd"] == 30.0
    assert p["kept_usd"] == 10.0 and p["profit_usd"] == 8.0      # the invoice is not money
    assert p["margin"] == 0.8 and p["human_hours"] == 2.0 and p["customers"] == 2
    assert p["cost_per_customer_usd"] == 1.0
    assert p["customer_acquisition_cost_usd"] is None             # nothing measured
    assert pnl(led, "other") == pnl(Ledger(tmp_path / "empty"), "x")


def test_finished_work_is_not_a_met_goal(tmp_path):
    j, (soft, music, tmpl) = three_missions(tmp_path)
    m = j.get(tmpl)
    m = j.run(m, J.agent_executor(tmp_path, j.audit, run_agent=agent(
        "Etsy lists planners at $12 (https://etsy.com/x)", ["planners at $12 https://etsy.com/x"])))
    assert m.status == "COMPLETED"
    goal = {x["mission_id"]: x["goal"] for x in J.portfolio(tmp_path, now=NOW)["missions"]}
    assert goal[tmpl] == {"metric": "revenue_usd", "at_least": 10.0, "by": None,
                          "measured": 0.0, "met": False}
    assert goal[soft] is None                                     # no goal set: not judged
    Ledger(tmp_path).sale(12.0, mission_id=tmpl)
    p = J.portfolio(tmp_path, now=NOW)
    assert next(x for x in p["missions"] if x["mission_id"] == tmpl)["goal"]["met"] is True
    assert tmpl not in [x["mission_id"] for x in p["missions"] if x["active"]]
    late = J.portfolio(tmp_path, now=dt.datetime(2027, 1, 2, tzinfo=dt.UTC))
    assert next(x for x in late["missions"] if x["mission_id"] == music)["goal"]["met"] is False
    assert "past its date" in next(x for x in late["missions"]
                                   if x["mission_id"] == music)["goal"]["note"]


def test_only_the_owner_sets_priority_budget_and_goal(tmp_path):
    j, (soft, _, _) = three_missions(tmp_path)
    for who in ("jarvis", "agent:researcher", "automaton"):
        with pytest.raises(PermissionError):
            J.set_mission(j, soft, who, budget_usd=100.0)
    with pytest.raises(ValueError):
        J.set_mission(j, soft, "human:owner", budget_usd=-1.0)
    with pytest.raises(ValueError):
        J.set_mission(j, soft, "human:owner", goal={"metric": "vibes", "at_least": 1})
    assert j.get(soft).budget_usd == 5.0
    assert '"mission.set"' in (tmp_path / "audit" / "chain.jsonl").read_text()


def test_a_mission_over_its_budget_does_not_run_and_a_step_past_it_pauses(tmp_path):
    j, (soft, music, _) = three_missions(tmp_path)
    Ledger(tmp_path).cost("model", 5.5, mission_id=soft)
    with pytest.raises(PermissionError, match="over its budget"):
        j.run(j.get(soft), J.agent_executor(tmp_path, j.audit, run_agent=agent("x", [])))
    assert j.get(soft).status == "READY"                          # refused, nothing changed
    b = Budgets(mission_caps=lambda mid: J.mission_budget(tmp_path, mid))
    led = Ledger(tmp_path)
    assert b.check(led, "researcher", 0.0, mission_id=music)[0]   # $0: free work still runs
    ok, why = b.check(led, "researcher", 0.01, mission_id=music)
    assert not ok and "budget $0.00" in why
    assert b.check(led, "researcher", 0.01, mission_id="msn_unset")[0]
    from bau.runtime import build_gateway  # the agents' real gateway
    real = build_gateway(tmp_path).budgets
    assert not real.check(led, "researcher", 0.01, mission_id=music)[0]


def test_old_and_newer_mission_rows_both_load(tmp_path):
    j = jarvis(tmp_path)
    j.store.append({"mission_id": "msn_old", "objective": "o", "mission_type": "research",
                    "status": "READY"})
    j.store.append({"mission_id": "msn_new", "objective": "o", "mission_type": "research",
                    "status": "READY", "a_field_from_later": 1})
    assert j.get("msn_old").priority == 0 and j.get("msn_old").budget_usd is None
    assert j.get("msn_new").status == "READY" and len(j.list()) == 2


def test_cli_and_jarvis(tmp_path, monkeypatch, capsys):
    from test_assistant import make

    from bau.assistant import TOOL_NODE
    from bau.cli import main
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    j, (soft, _, _) = three_missions(tmp_path)
    JobStore(tmp_path).create(soft, "o", "researcher", [])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert main(["mission", "set", soft, "--budget", "50"]) != 0
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    assert main(["mission", "set", soft, "--priority", "9", "--goal-profit", "100",
                 "--by", "2027-03-01"]) == 0
    assert j.get(soft).goal == {"metric": "profit_usd", "at_least": 100.0, "by": "2027-03-01"}
    capsys.readouterr()
    assert main(["mission", "portfolio"]) == 0
    assert soft in capsys.readouterr().out
    a = make(tmp_path)
    assert a.tools["portfolio"].kind == "read" and TOOL_NODE["portfolio"] == "strategist"
    out, err = a._run_tool("portfolio", {})
    assert not err and out["missions"][0]["mission_id"] == soft
    assert out["missions"][0]["jobs"][0]["agent"] == "researcher"
