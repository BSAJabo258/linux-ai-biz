"""Jarvis knows the automaton (the owner, 2026-11-11: "make sure Jarvis is up to the new code
... like automaton"). Before this, the automaton reached Jarvis only through the briefing; asked
in conversation, he had no tool for it. One read tool joins the automaton's survival state and
the mission portfolio; the small model is handed it when the owner mentions either. Starting,
stopping, reviving and growing it stay the owner's."""

import datetime as dt

from test_jarvis_lean import lean
from test_mission_run import jarvis

from bau import automaton as M
from bau import jarvis as J
from bau.economics import Ledger


def test_off_it_says_so_and_who_starts_it(tmp_path):
    out = lean(tmp_path, ["ok"]).t_automaton()
    assert list(out)[0] == "say"                       # a small model reads the start first
    assert "not running" in out["say"] and "bau automaton start" in out["say"]
    assert out["automaton"] == {"on": False} and out["portfolio"]["active"] == 0


def test_running_it_reports_its_money_days_and_missions(tmp_path):
    now = dt.datetime.now(dt.UTC)
    M.start(tmp_path, "human:owner", "subscribers", 2, now=now - dt.timedelta(days=3),
            reinvest_pct=50, reinvest_cap_usd=10)
    Ledger(tmp_path).sale(20.0, factory="fanvue", platform_fee=4.0,
                          when=now - dt.timedelta(days=1))
    j = jarvis(tmp_path)
    m = j.plan("price a template pack", "research", {})
    J.set_mission(j, m.mission_id, "human:owner", priority=2,
                  goal={"metric": "profit_usd", "at_least": 50})
    out = lean(tmp_path, ["ok"]).t_automaton()
    s = out["say"]
    assert "running" in s and "day 4" in s and "kept so far: $16.00" in s and "normal" in s
    assert "Spending money left: $8.00" in s and "next 29 days" in s
    assert "1 active mission" in s
    top = out["portfolio"]["top"][0]
    assert top["mission_id"] == m.mission_id and top["goal_met"] is False
    assert out["automaton"]["tier"] == "normal"
    assert "the owner" in out["owner_only"]


def test_dead_it_says_why_and_that_only_the_owner_revives_it(tmp_path):
    t0 = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    M.start(tmp_path, "human:owner", "subscribers", 2, now=t0)
    M.check(tmp_path, t0 + dt.timedelta(days=31))
    out = lean(tmp_path, ["ok"]).t_automaton()
    assert "dead" in out["say"] and "no income in 30 days" in out["say"]
    assert "only you" in out["say"].lower()


def test_jarvis_cannot_start_or_stop_it(tmp_path):
    a = lean(tmp_path, ["ok"])
    assert a.tools["automaton"].kind == "read"
    assert not any(n.startswith(("automaton_start", "start_automaton", "automaton_stop"))
                   for n in a.tools)


def test_asked_about_the_automaton_the_small_model_sees_it(tmp_path):
    for q in ("how is the automaton doing?", "show me the portfolio",
              "what survival tier are we in?"):
        r = lean(tmp_path, ["It is not running."]).ask(q)
        assert any(c["tool"] == "automaton" for c in r.cards), q
