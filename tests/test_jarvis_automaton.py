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
    Ledger(tmp_path).cost("model", 3.0, when=now - dt.timedelta(hours=12))
    Ledger(tmp_path).sale(100.0, factory="fanvue", platform_fee=20.0,   # before this start
                          when=now - dt.timedelta(days=10))
    j = jarvis(tmp_path)
    m = j.plan("price a template pack", "research", {})
    J.set_mission(j, m.mission_id, "human:owner", priority=2,
                  goal={"metric": "profit_usd", "at_least": 50})
    out = lean(tmp_path, ["ok"]).t_automaton()
    s = out["say"]
    assert "running" in s and "day 4" in s and "money kept: $16.00" in s and "normal" in s
    assert "spent: $3.00" in s and "Spending money left: $5.00" in s and "next 29 days" in s
    assert "Since this start" in s and "Across the whole ledger" in s
    assert "kept $96.00" in s                          # the whole ledger has the older $80
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
    # Its death set a HOLD and start needs the owner's audience and number: both said.
    assert "bau governor release, then bau automaton start --audience" in out["say"]


def test_stopped_it_gives_the_terminal_command_not_the_finished_card(tmp_path):
    M.start(tmp_path, "human:owner", "subscribers", 2)
    M.stop(tmp_path, "human:owner")
    s = lean(tmp_path, ["ok"]).t_automaton()["say"]
    assert "not running" in s and "bau automaton start --audience" in s and "card" not in s


def test_on_but_held_it_says_nothing_posts(tmp_path):
    from bau.governor import Governor
    M.start(tmp_path, "human:owner", "subscribers", 2)
    Governor(tmp_path).hold("checking a complaint", by="human:owner")
    s = lean(tmp_path, ["ok"]).t_automaton()["say"]
    assert "Blocked by a HOLD (checking a complaint)" in s and "running" not in s
    assert "autopost" not in s                         # autopost is on: only the HOLD blocks


def test_an_unreadable_portfolio_keeps_the_status_and_never_says_zero(tmp_path, monkeypatch):
    M.start(tmp_path, "human:owner", "subscribers", 2)

    def broken(home, now=None):
        raise OSError("missions.jsonl unreadable")
    monkeypatch.setattr(J, "portfolio", broken)
    out = lean(tmp_path, ["ok"]).t_automaton()
    assert "running" in out["say"] and "could not be read" in out["say"]
    assert out["portfolio"] == {"unavailable": True} and "0 active" not in out["say"]


def test_jarvis_cannot_start_or_stop_it(tmp_path):
    a = lean(tmp_path, ["ok"])
    assert a.tools["automaton"].kind == "read"
    assert not any(n.startswith(("automaton_start", "start_automaton", "automaton_stop"))
                   for n in a.tools)


def test_asked_about_the_automaton_the_small_model_sees_it(tmp_path):
    for q in ("how is the automaton doing?", "what survival tier are we in?"):
        r = lean(tmp_path, ["It is not running."]).ask(q)
        assert any(c["tool"] == "automaton" for c in r.cards), q
    # A portfolio question gets the whole portfolio (goal-met missions too), not the
    # automaton's top three; "tier" alone (a free tier) is not the automaton.
    r = lean(tmp_path, ["None yet."]).ask("which portfolio missions met their goal?")
    assert [c["tool"] for c in r.cards][:1] == ["portfolio"]
    r = lean(tmp_path, ["Yes."]).ask("do we have tools to stay on the free tier?")
    assert not any(c["tool"] == "automaton" for c in r.cards)


def test_on_with_autopost_off_it_says_nothing_posts(tmp_path):
    from bau.fanvue import set_autopost
    M.start(tmp_path, "human:owner", "subscribers", 2)
    set_autopost(tmp_path, False, "human:owner")
    s = lean(tmp_path, ["ok"]).t_automaton()["say"]
    assert "autopost is off" in s and "bau fanvue autopost on" in s and "running" not in s


def test_stopped_and_held_it_says_both(tmp_path):
    from bau.governor import Governor
    M.start(tmp_path, "human:owner", "subscribers", 2)
    M.stop(tmp_path, "human:owner")
    Governor(tmp_path).hold("checking a complaint", by="human:owner")
    s = lean(tmp_path, ["ok"]).t_automaton()["say"]
    assert "not running" in s and "HOLD (checking a complaint)" in s
    assert "bau governor release" in s


def test_held_with_autopost_off_names_both_blockers(tmp_path):
    from bau.fanvue import set_autopost
    from bau.governor import Governor
    M.start(tmp_path, "human:owner", "subscribers", 2)
    set_autopost(tmp_path, False, "human:owner")
    Governor(tmp_path).hold("checking a complaint", by="human:owner")
    s = lean(tmp_path, ["ok"]).t_automaton()["say"]
    assert "HOLD (checking a complaint)" in s and "bau fanvue autopost on" in s


def test_a_broken_autopost_file_keeps_the_status(tmp_path):
    M.start(tmp_path, "human:owner", "subscribers", 2)
    (tmp_path / "fanvue" / "autopost.json").write_text("[1, 2]")
    out = lean(tmp_path, ["ok"]).t_automaton()
    assert "missing or unreadable" in out["say"] and out["automaton"]["on"] is True
    assert "Missions:" in out["say"]


def test_a_mission_objective_never_puts_a_week_card_up(tmp_path):
    from test_week import plan
    name = plan(tmp_path)
    j = jarvis(tmp_path)
    j.plan(f"schedule the week {name}", "research", {})     # stored text, not the owner's ask
    r = lean(tmp_path, ["Here it is."]).ask("how is the automaton doing?")
    assert not any(p["tool"] == "schedule_week" for p in r.pending)
