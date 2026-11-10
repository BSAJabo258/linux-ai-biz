"""The automaton (src/bau/automaton.py, the owner's choice 2026-11-10: "make money or die",
full automaton, $0 budget): the owner switches it on, the feed queues posts without the Accept
card, hosted models are skipped while the budget is $0, and it dies (governor HOLD, autopost
off) after 30 days without income or on any spending past its budget."""

import datetime as dt
import json

import pytest
from test_creator_feed import fake_draw, home  # noqa: F401 - the shared fixture

from bau import automaton as M
from bau import autopilot as A
from bau import creator_feed as C
from bau import fanvue as F
from bau.governor import hold_reason
from bau.models.providers import ScriptedProvider

T0 = dt.datetime(2026, 11, 10, 12, tzinfo=dt.UTC)


def day(n):
    return T0 + dt.timedelta(days=n)


def ledger(home, name, when, usd):  # noqa: F811
    p = home / "economics" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps({"ts": when.isoformat(), "kind": "x", "usd": usd}) + "\n")


def test_only_the_owner_switches_it_on_and_it_turns_autopost_on(home):  # noqa: F811
    with pytest.raises(PermissionError):
        M.start(home, "jarvis", "subscribers", 3)
    s = M.start(home, "human:owner", "subscribers", 3, now=T0)
    assert s["on"] and s["budget_usd"] == 0 and s["die_after_days"] == 30
    assert F.autopost_choice(home)["on"] and M.free_only(home)
    with pytest.raises(PermissionError):
        M.stop(home, "automaton")
    M.stop(home, "human:owner")
    assert not M.running(home) and not F.autopost_choice(home)["on"]


def test_thirty_days_without_income_and_it_dies(home):  # noqa: F811
    M.start(home, "human:owner", "subscribers", 3, now=T0)
    assert not M.check(home, day(29)).get("dead") and hold_reason(home) is None
    s = M.check(home, day(30))
    assert s["dead"]["why"] == "no income in 30 days"
    assert "automaton died" in hold_reason(home)                 # HOLD: only read-only runs
    assert not F.autopost_choice(home)["on"] and not M.running(home)
    from bau.status import dashboard
    assert any(i["color"] == "RED" and i["item"].startswith("automaton died")
               for i in dashboard(home)["items"])


def test_income_resets_the_clock(home):  # noqa: F811
    M.start(home, "human:owner", "subscribers", 3, now=T0)
    ledger(home, "revenue.jsonl", day(20), 4.99)
    s = M.check(home, day(45))
    assert not s.get("dead") and s["income_usd"] == 4.99 and s["days_left_to_earn"] == 5.0
    assert M.check(home, day(50))["dead"]["why"] == "no income in 30 days"


def test_spending_past_a_zero_budget_kills_it(home):  # noqa: F811
    M.start(home, "human:owner", "subscribers", 3, now=T0)
    ledger(home, "costs.jsonl", day(-1), 9.0)                    # before its start: not counted
    assert not M.check(home, day(1)).get("dead")
    ledger(home, "costs.jsonl", day(2), 0.0008)                  # one paid model call
    assert M.check(home, day(3))["dead"]["why"].startswith("spent $0.00")


def test_while_it_runs_the_feed_queues_posts_without_the_accept_card(home, monkeypatch):  # noqa: F811
    from bau import team
    monkeypatch.setattr(team, "show", lambda h: {"boss": "qwen3.5-9b"})
    M.start(home, "human:owner", "subscribers", 2)
    assert C.fill(home) == 2                                     # two draft jobs queued
    model = ScriptedProvider(["Golden hour on the roof."] * 2)
    A.run(home, {"draft": lambda t: C.make_post(home, t, draw=fake_draw([]),
                                               factory=lambda m, h: (model, {}))}, max_steps=4)
    assert F.Queue(home).review() == []
    pending = F.Queue(home).pending()
    assert len(pending) == 2 and all(F.AI_LABEL in i["caption"] for i in pending)


def test_a_zero_budget_uses_only_this_computers_models(home, monkeypatch):  # noqa: F811
    from bau import assistant
    seen = []

    class Hosted:
        waits = 1

    def provider_for(mid, h):
        seen.append(mid)
        local = mid == "qwen3.5-9b"
        return (object() if local else Hosted()), {
            "deployment": "local" if local else "hosted", "api_key_env": None}
    monkeypatch.setattr("bau.runtime.provider_for", provider_for)
    M.start(home, "human:owner", "subscribers", 1)
    _, rec = assistant.pick_model(home)
    assert rec["deployment"] == "local"
    M.stop(home, "human:owner")
    _, rec = assistant.pick_model(home)
    assert rec["deployment"] == "hosted"                         # off: the owner's usual order
