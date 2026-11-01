"""Harness step 1 (docs/HARNESS-MAP.md): Jarvis's tools go through the Universal Gateway, the
same path the agents use, so HOLD, permissions, network trust, budget and the audit chain
apply to him too. Before this, his 36 tools had their own table and skipped all of it.
Confirm tools still only stage a card for the owner. Written before the code."""

from test_assistant import events, make

from bau import network
from bau.governor import Governor
from bau.network import NetworkFacts, Trust, TrustPolicy


def test_every_tool_call_goes_through_the_gateway(tmp_path):
    a = make(tmp_path, script=[{"tool": "system_status", "input": {}}, "All fine."])
    a.ask("status?")
    rows = events(tmp_path, "gateway.invoked")
    assert [r["data"]["capability"] for r in rows] == ["inspect.jarvis.system_status"]
    assert rows[0]["actor"] == "jarvis"


def test_the_gateway_lists_every_jarvis_tool(tmp_path):
    a = make(tmp_path)
    caps = {c["capability"] for c in a.gateway.catalog()}
    for t in a.tools.values():
        if t.kind in ("read", "act") and t.name not in ("tool_menu", "use_tool"):
            assert any(c.endswith(f".jarvis.{t.name}") for c in caps), t.name


def test_hold_stops_his_act_tools_but_not_reading_or_holding(tmp_path):
    Governor(tmp_path, audit=make(tmp_path).audit, systemctl="").hold("test", by="human:owner")
    a = make(tmp_path)
    out, err = a._run_tool("remember", {"title": "x", "note": "y"})
    assert err and "HOLD" in out["error"]
    assert not (tmp_path / "memory" / "records").exists() or \
        not list((tmp_path / "memory" / "records").glob("*.md"))
    assert events(tmp_path, "gateway.denied")[-1]["data"]["step"] == "governor_hold"
    out, err = a._run_tool("system_status", {})
    assert not err
    out, err = a._run_tool("hold_everything", {"reason": "again"})    # makes BAU safer
    assert not err


def test_confirm_tools_still_only_stage_a_card(tmp_path):
    a = make(tmp_path)
    out, err = a._run_tool("release_hold", {})
    assert not err and out["pending_id"] in a.pending
    assert not events(tmp_path, "gateway.invoked")


def test_offline_his_local_tools_work_and_web_tools_say_why(tmp_path):
    a = make(tmp_path, trust=lambda: Trust.OFFLINE)
    out, err = a._run_tool("recall", {"query": "anything"})
    assert not err
    out, err = a._run_tool("web_search", {"query": "x", "why": "test"})
    assert err and "offline" in out["error"]


def test_his_local_tools_never_check_the_network(tmp_path):
    def boom():
        raise AssertionError("a local tool asked about the network")
    a = make(tmp_path, trust=boom)
    out, err = a._run_tool("usage_today", {})
    assert not err


def test_an_unknown_wired_network_counts_like_unknown_wifi(tmp_path):
    # Online by cable with no Wi-Fi name was rated below coffee-shop Wi-Fi, so even
    # read-only internet actions were refused on the owner's wired desktop.
    p = TrustPolicy(tmp_path / "networks.yaml")
    assert p.classify(NetworkFacts(online=True, wired=True)) == Trust.UNTRUSTED
    assert network.allows(p.classify(NetworkFacts(online=True, wired=True)), "READ_ONLY")
    assert p.classify(NetworkFacts(online=False)) == Trust.OFFLINE


def test_a_network_that_blocks_outside_dns_is_still_online(monkeypatch):
    monkeypatch.setattr(network, "_reachable", lambda h, p, t=2.0: p == 443)
    assert network.is_online()
    monkeypatch.setattr(network, "_reachable", lambda h, p, t=2.0: False)
    assert not network.is_online()


# Code review of step 1 (2026-11-01): with Jarvis's model spend over the default budget
# ($2/hour), every Jarvis tool was refused at the budget step, hold_everything included.
def test_free_tools_and_holding_are_never_stopped_by_the_budget(tmp_path):
    from bau.economics import Ledger
    Ledger(tmp_path).cost("model", 25.0, agent="jarvis", provider="anthropic")
    a = make(tmp_path)
    out, err = a._run_tool("system_status", {})
    assert not err
    out, err = a._run_tool("hold_everything", {"reason": "over budget"})
    assert not err


def test_hold_runs_on_hold_without_pretending_to_be_read_only(tmp_path):
    a = make(tmp_path)
    row = next(c for c in a.gateway.catalog()
               if c["capability"] == "change.jarvis.hold_everything")
    assert row["level"] == "LOW_RISK"


def test_the_quick_hold_reply_tells_the_truth(tmp_path, monkeypatch):
    a = make(tmp_path)                        # plain mode: no model
    monkeypatch.setattr(a, "_run_tool", lambda n, args: ({"error": "not run: test"}, True))
    r = a.ask("stop everything")
    assert "couldn't" in r.text.lower() and "everything's on hold" not in r.text.lower()


def test_world_watch_can_answer_from_its_cache_offline(tmp_path):
    a = make(tmp_path, trust=lambda: Trust.OFFLINE)
    assert a.caps["world_watch"] in {c["capability"] for c in a.gateway.catalog()
                                     if not c["needs_network"]}


def test_the_network_is_asked_at_most_once_a_minute(tmp_path):
    asked = []
    a = make(tmp_path, trust=lambda: asked.append(1) or Trust.UNTRUSTED)
    for _ in range(3):
        a._run_tool("web_search", {"query": "x", "why": "test"})
    assert len(asked) == 1
