"""The team: Qwen is the boss. The owner names a boss (a local model that uses tools: it runs
Jarvis and the agents), a thinker (the local uncensored model: unfiltered ideas, text only,
never tools, never kids) and a specialist on call (Claude: only when the boss is stuck, or
to double-check). A supervisor stops loops, hands a stuck job to the specialist (on its own
within the owner's daily limit, or only after the owner says so), flags facts no tool
result backs, and keeps a score sheet per model. Written before the code it tests."""

import json

import pytest

from bau import agentfolders as AF
from bau import agents, network
from bau import brains as B
from bau import supervisor as S
from bau import team as T
from bau.audit import AuditLog
from bau.models.providers import ScriptedProvider
from bau.registry import CapabilityRegistry

BASE = {"name": "m", "version": "1", "source": "test", "license": "Apache-2.0",
        "commercial_use": True, "privacy": "local", "context": 8192, "input_types": ["text"],
        "quality": 0.5, "latency_ms": 100, "cost_in_per_mtok": 0, "cost_out_per_mtok": 0}
QWEN = {**BASE, "model_id": "qwen-boss", "provider": "local", "deployment": "local",
        "trust_level": "QUANTIZED", "tools": True, "status": "APPROVED",
        "benchmark": {"reply_ok": True, "tool_calls": True}}
CLAUDE = {**BASE, "model_id": "claude-test", "provider": "anthropic", "deployment": "api",
          "trust_level": "OFFICIAL", "privacy": "vendor", "tools": True, "status": "APPROVED"}
UNC = {**BASE, "model_id": "qwen-unc", "provider": "local", "deployment": "local",
       "trust_level": "ABLITERATED", "tools": False, "status": "APPROVED",
       "lane": "content_only", "use_for": ["ideas", "script"],
       "benchmark": {"reply_ok": True}}

AGENT = """---
name: shop-researcher
description: Finds suppliers and prices for the shop, with a source for every fact.
brain: small
tools: [memory.search]
max_steps: 8
---
# Shop researcher

Research what the owner asks.
"""
LOOP = {"tool": "memory__search", "input": {"query": "mugs"}}


def home_with_team(tmp_path, takeover="auto"):
    reg = CapabilityRegistry(tmp_path / "registry" / "capabilities.yaml")
    for r in (QWEN, CLAUDE, UNC):
        reg.add("model", r)
    audit = AuditLog(tmp_path / "audit" / "chain.jsonl", key=b"")
    T.set_team(tmp_path, "human:owner", audit, boss="qwen-boss", thinker="qwen-unc",
               specialist="claude-test", takeover=takeover)
    return audit


def factory_for(scripts):
    made = {}

    def factory(mid, home):
        rec = CapabilityRegistry(home / "registry" / "capabilities.yaml").data["model"][mid]
        made.setdefault(mid, ScriptedProvider(list(scripts.get(mid, []))))
        return made[mid], rec
    factory.made = made
    return factory


def agent(home, audit):
    d = home / "agents" / "shop-researcher"
    d.mkdir(parents=True)
    (d / "AGENT.md").write_text(AGENT)
    AF.approve("shop-researcher", "human:owner", home, audit)


def result(status="COMPLETED", text="", evidence=(), calls=()):
    return agents.RunResult(status, text, len(calls), list(calls), 0.0, 0,
                            evidence=list(evidence))


# ------------------------------------------------------------------ loops stop early

def test_a_model_repeating_the_same_tool_call_is_stopped_as_looping(tmp_path):
    audit = home_with_team(tmp_path)
    agent(tmp_path, audit)
    boss = ScriptedProvider([LOOP] * 8)
    res = AF.run("shop-researcher", "find mugs", tmp_path, audit,
                 brains=(boss, {**QWEN, "id": "qwen-boss"}),
                 trust=lambda: network.Trust.TRUSTED)
    assert res.status == "LOOPING"
    assert res.steps == agents.LOOP_LIMIT                    # stopped at 3, not after 8
    assert len(boss.calls) == agents.LOOP_LIMIT


def test_tool_results_are_kept_as_evidence(tmp_path):
    audit = home_with_team(tmp_path)
    agent(tmp_path, audit)
    boss = ScriptedProvider([LOOP, "Found it."])
    res = AF.run("shop-researcher", "find mugs", tmp_path, audit,
                 brains=(boss, {**QWEN, "id": "qwen-boss"}),
                 trust=lambda: network.Trust.TRUSTED)
    assert res.status == "COMPLETED" and len(res.evidence) == 1


# ------------------------------------------------------------------ facts need a source

def test_facts_no_tool_result_backs_are_flagged_unchecked():
    evidence = ["Supplier A sells mugs at $4.20, see https://a.example/mugs"]
    answer = ('Supplier A charges $4.20 (https://a.example/mugs). Supplier B charges $3.10 '
              'and says "free shipping over 50 units", see https://b.example.')
    flagged = S.unchecked(answer, evidence)
    assert "$3.10" in flagged and "https://b.example" in flagged
    assert "free shipping over 50 units" in flagged
    assert "$4.20" not in flagged and "https://a.example/mugs" not in flagged
    assert S.unchecked("All good, nothing to report.", []) == []


# ------------------------------------------------------------------ the specialist on call

def test_a_stuck_boss_hands_the_job_to_the_specialist_with_what_it_tried():
    seen = []

    def specialist(task):
        seen.append(task)
        return result(text="Two suppliers, sources attached.")
    out = S.supervise("find mugs", lambda t: result("LOOPING", calls=[{"capability":
                                                    "memory.search", "ok": True}]),
                      specialist, mode="auto")
    assert out.status == "COMPLETED" and out.supervision["by"] == "specialist"
    assert out.supervision["handed_over"] == "LOOPING"
    assert "find mugs" in seen[0] and "memory.search" in seen[0] and "LOOPING" in seen[0]


def test_in_ask_mode_the_owner_decides_before_any_paid_model_runs():
    called = []
    out = S.supervise("find mugs", lambda t: result("STEP_LIMIT"),
                      lambda t: called.append(t), mode="ask")
    assert not called
    assert out.status == "NEEDS_OWNER"
    assert "bau team set --takeover auto" in out.supervision["next"]


def test_the_owners_daily_limit_stops_a_takeover():
    called = []
    out = S.supervise("find mugs", lambda t: result("LOOPING"), lambda t: called.append(t),
                      mode="auto", over_limit=lambda: "We've reached today's limit you set")
    assert not called and out.status == "NEEDS_OWNER"
    assert "limit" in out.supervision["next"]


def test_a_finished_boss_answer_is_kept_and_its_unbacked_facts_flagged():
    out = S.supervise("price?", lambda t: result(text="It costs $9.99.", evidence=["$5"]),
                      None, mode="auto")
    assert out.status == "COMPLETED" and out.supervision["by"] == "boss"
    assert out.supervision["unchecked"] == ["$9.99"]


def test_a_double_check_by_the_specialist():
    ok = S.supervise("price?", lambda t: result(text="It costs $5.", evidence=["$5"]),
                     None, mode="auto", verify=lambda answer, ev: "OK")
    assert ok.supervision["double_check"] == "OK"
    bad = S.supervise("price?", lambda t: result(text="It costs $5.", evidence=["$5"]),
                      None, mode="auto", verify=lambda answer, ev: "The source says $6.")
    assert bad.supervision["double_check"] == "The source says $6."
    asked = S.supervise("price?", lambda t: result(text="It costs $5."), None, mode="ask",
                        verify=lambda answer, ev: pytest.fail("no paid check in ask mode"))
    assert "not double-checked" in asked.supervision["double_check"]


# ------------------------------------------------------------------ the team, set by the owner

def test_the_owner_sets_the_team_and_qwen_runs_jarvis(tmp_path):
    from bau.assistant import pick_model
    home_with_team(tmp_path)
    t = T.show(tmp_path)
    assert (t["boss"], t["thinker"], t["specialist"], t["takeover"]) == (
        "qwen-boss", "qwen-unc", "claude-test", "auto")
    assert B.config(tmp_path)["small"] == "qwen-boss"            # the agents' brain too
    assert B.config(tmp_path)["strong"] == "claude-test"
    assert B.config(tmp_path)["content"] == "qwen-unc"
    provider, rec = pick_model(tmp_path)
    assert rec["id"] == "qwen-boss"                              # Jarvis thinks with Qwen


def test_only_the_owner_sets_the_team_and_the_uncensored_model_never_holds_tools(tmp_path):
    home_with_team(tmp_path)
    with pytest.raises(PermissionError):
        T.set_team(tmp_path, "agent:jarvis", None, boss="claude-test")
    with pytest.raises(ValueError, match="content lane"):
        T.set_team(tmp_path, "human:owner", None, boss="qwen-unc")
    with pytest.raises(ValueError, match="content lane"):
        T.set_team(tmp_path, "human:owner", None, specialist="qwen-unc")
    with pytest.raises(ValueError):
        T.set_team(tmp_path, "human:owner", None, takeover="always")
    assert T.show(tmp_path)["boss"] == "qwen-boss"


def test_takeover_waits_for_the_owner_until_they_choose(tmp_path):
    reg = CapabilityRegistry(tmp_path / "registry" / "capabilities.yaml")
    reg.add("model", QWEN)
    assert T.show(tmp_path)["takeover"] == "ask"


# ------------------------------------------------------------------ agents run under the boss

def test_an_agent_on_the_boss_that_loops_is_finished_by_the_specialist(tmp_path):
    audit = home_with_team(tmp_path, takeover="auto")
    agent(tmp_path, audit)
    factory = factory_for({"qwen-boss": [LOOP] * 8,
                           "claude-test": ["Two suppliers, each with a source."]})
    res = AF.run("shop-researcher", "find mugs", tmp_path, audit, factory=factory,
                 trust=lambda: network.Trust.TRUSTED)
    assert res.status == "COMPLETED" and "Two suppliers" in res.final_text
    assert res.supervision["by"] == "specialist" and res.supervision["handed_over"] == "LOOPING"
    rows = T.scores(tmp_path)
    by = {r["model"]: r for r in rows}
    assert by["qwen-boss"]["looped"] == 1 and by["qwen-boss"]["handed_over"] == 1
    assert by["claude-test"]["finished"] == 1
    assert any(r["event"] == "team.takeover" for r in audit.records())


def test_a_specialist_that_cannot_start_is_reported_not_crashed(tmp_path):
    audit = home_with_team(tmp_path, takeover="auto")
    agent(tmp_path, audit)
    inner = factory_for({"qwen-boss": [LOOP] * 8})

    def factory(mid, home):
        if mid == "claude-test":
            raise PermissionError("claude-test needs its API key")
        return inner(mid, home)
    res = AF.run("shop-researcher", "find mugs", tmp_path, audit, factory=factory,
                 trust=lambda: network.Trust.TRUSTED)
    assert res.status == "FAILED" and "API key" in res.final_text


def test_in_ask_mode_the_agent_stops_and_says_what_it_needs(tmp_path):
    audit = home_with_team(tmp_path, takeover="ask")
    agent(tmp_path, audit)
    factory = factory_for({"qwen-boss": [LOOP] * 8})
    res = AF.run("shop-researcher", "find mugs", tmp_path, audit, factory=factory,
                 trust=lambda: network.Trust.TRUSTED)
    assert res.status == "NEEDS_OWNER"
    assert "claude-test" not in factory.made                     # no paid call


# ------------------------------------------------------------------ the thinker

def test_the_thinker_gives_unfiltered_ideas_as_text_only(tmp_path):
    audit = home_with_team(tmp_path)
    factory = factory_for({"qwen-unc": ["Raise the price; nobody compares mug prices."]})
    out = T.think(tmp_path, "How do we sell more mugs?", "Sales: 40 mugs in May.",
                  factory=factory, audit=audit)
    assert out["thinker"] == "qwen-unc" and "Raise the price" in out["ideas"]
    call = factory.made["qwen-unc"].calls[0]
    assert call["tools"] == []                                   # never tools
    assert "untrusted_data" in json.dumps(call["messages"])      # material is data
    assert out["for_boss"].startswith("<untrusted_data")         # advice, never orders
    assert any(r["event"] == "model.content_lane" for r in audit.records())


def test_the_thinker_never_works_on_kids_content_or_without_the_ideas_job(tmp_path):
    home_with_team(tmp_path)
    factory = factory_for({"qwen-unc": ["x"]})
    with pytest.raises(PermissionError):
        T.think(tmp_path, "Ideas for our kids channel?", factory=factory)
    # Audit 2026-10-25: these slipped through the older word list.
    for q in ("A song for 4-year-olds", "little ones aged 3 to 5",
              "Benny the Bear counting series (ages 2-4)"):
        with pytest.raises(PermissionError):
            T.think(tmp_path, q, factory=factory)
    reg = CapabilityRegistry(tmp_path / "registry" / "capabilities.yaml")
    reg.add("model", {**UNC, "use_for": ["script"]})
    with pytest.raises(ValueError, match="ideas"):
        T.think(tmp_path, "How do we sell more mugs?", factory=factory)


# ------------------------------------------------------------------ Jarvis, CLI, docs

def test_the_shipped_uncensored_qwen_can_be_the_thinker_and_nothing_else():
    import yaml

    from bau.home import shipped_data
    rec = yaml.safe_load((shipped_data() / "registry_defaults.yaml").read_text())[
        "model"]["qwen3-4b-heretic-content"]
    assert "ideas" in rec["use_for"] and rec["lane"] == "content_only"
    assert rec["tools"] is False and rec["status"] == "REGISTERED"     # owner benches first


def test_jarvis_asks_the_thinker_and_reports_supervision(tmp_path):
    from bau.assistant import TOOL_NODE, Assistant
    audit = home_with_team(tmp_path)
    factory = factory_for({"qwen-unc": ["Bundle mugs with coasters."]})
    a = Assistant(tmp_path, ScriptedProvider(["ok"]), {**QWEN, "id": "qwen-boss"},
                  "human:owner", audit, clients={"model_factory": factory})
    assert a.tools["ask_thinker"].kind == "read" and TOOL_NODE["ask_thinker"] == "strategist"
    out, err = a._run_tool("ask_thinker", {"question": "How do we sell more mugs?"})
    assert not err and "coasters" in out["ideas"]


def test_cli(tmp_path, monkeypatch, capsys):
    from bau.cli import main
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    reg = CapabilityRegistry(tmp_path / "registry" / "capabilities.yaml")
    for r in (QWEN, CLAUDE, UNC):
        reg.add("model", r)
    monkeypatch.setattr("bau.cli_ext._human", lambda: "human:owner")
    assert main(["team", "set", "--boss", "qwen-boss", "--thinker", "qwen-unc",
                 "--specialist", "claude-test", "--takeover", "auto"]) == 0
    capsys.readouterr()
    assert main(["team", "show"]) == 0
    assert json.loads(capsys.readouterr().out)["boss"] == "qwen-boss"
    assert main(["team", "score"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_docs_explain_the_team():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    doc = (root / "docs" / "TEAM.md").read_text()
    for need in ("bau team set", "bau team show", "bau team score", "--takeover",
                 "never holds tools", "bau models bench"):
        assert need in doc, need
    assert "docs/TEAM.md" in (root / "CLAUDE.md").read_text()
