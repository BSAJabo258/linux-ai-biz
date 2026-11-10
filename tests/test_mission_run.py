"""Missions run (the audit, 2026-11-10: planned missions never ran; `bau mission` had no run).
A READY research mission goes to the researcher agent; it is COMPLETED only when every fact in
the agent's answer is backed by what its tools returned, otherwise PAUSED for the owner. In
the chat, run_mission is staged and runs on the owner's Accept. Fake agent only."""

import pytest
from test_assistant import make

from bau.agents import RunResult
from bau.jarvis import Jarvis, agent_executor
from bau.policy import PolicyEngine
from bau.regulations import Registry


def jarvis(home):
    return Jarvis(PolicyEngine.load(Registry.load()), home=home)


def agent(text, evidence, status="COMPLETED"):
    def run(name, objective, mission_id):
        assert name == "researcher"
        return RunResult(status, text, 3, [{"capability": "memory.search", "ok": True}], 0.0, 0,
                         evidence)
    return run


def test_a_research_mission_backed_by_its_tools_completes_with_evidence(tmp_path):
    j = jarvis(tmp_path)
    m = j.plan("research open source video tools", "research", {})
    assert m.status == "READY"
    m = j.run(m, agent_executor(tmp_path, j.audit, run_agent=agent(
        "Remotion has 21,000 stars: https://github.com/remotion-dev/remotion",
        ["remotion-dev/remotion stars 21,000 https://github.com/remotion-dev/remotion"])))
    assert m.status == "COMPLETED" and m.steps["verify"] is True and m.evidence
    assert m.steps["execute"]["tools_used"] == ["memory.search"]


def test_a_fact_no_tool_backs_pauses_the_mission_for_the_owner(tmp_path):
    j = jarvis(tmp_path)
    m = j.plan("research open source video tools", "research", {})
    m = j.run(m, agent_executor(tmp_path, j.audit, run_agent=agent(
        "Remotion has 99,000 stars.", ["remotion-dev/remotion stars 21,000"])))
    assert m.status == "PAUSED" and m.steps["verify"] is False
    assert "99,000" in m.steps["execute"]["why_not_verified"]
    m2 = j.plan("q", "research", {})
    m2 = j.run(m2, agent_executor(tmp_path, j.audit, run_agent=agent("", [], "STEP_LIMIT")))
    assert m2.status == "PAUSED" and "STEP_LIMIT" in m2.steps["execute"]["why_not_verified"]


def test_only_missions_an_agent_can_do_run(tmp_path):
    from bau.jarvis import Mission
    j = jarvis(tmp_path)
    m = Mission("msn_test", "send the campaign", "send_email_campaign", status="READY")
    with pytest.raises(PermissionError):
        j.run(m, agent_executor(tmp_path, j.audit, run_agent=agent("x", [])))


def test_in_the_chat_a_mission_runs_only_on_the_owners_accept(tmp_path):
    j = jarvis(tmp_path)
    mid = j.plan("research open source video tools", "research", {}).mission_id
    a = make(tmp_path, [{"tool": "run_mission", "input": {"mission_id": mid}}, "Staged."],
             clients={"mission_runner": agent(
                 "Remotion: https://github.com/remotion-dev/remotion",
                 ["https://github.com/remotion-dev/remotion"])})
    r = a.ask("run the video tools mission")
    assert r.pending and j.get(mid).status == "READY"            # nothing ran yet
    out = a.confirm(r.pending[0]["id"], True, "human:owner")
    assert out["result"]["status"] == "COMPLETED" and j.get(mid).status == "COMPLETED"


def test_a_mission_that_is_not_ready_is_not_even_offered(tmp_path):
    a = make(tmp_path, ["ok"])
    with pytest.raises(ValueError):
        a._stage_mission("msn_nope")


def test_hold_stops_a_mission(tmp_path):
    from bau.governor import Governor
    j = jarvis(tmp_path)
    m = j.plan("research", "research", {})
    Governor(tmp_path).hold("test")
    with pytest.raises(PermissionError):
        j.run(m, agent_executor(tmp_path, j.audit, run_agent=agent("x", [])))


def test_an_answer_of_questions_is_not_a_finished_mission(tmp_path):
    # Real model, 2026-11-10: "research open source video tools" came back as clarifying
    # questions only: nothing false, nothing found. That is not done.
    j = jarvis(tmp_path)
    m = j.plan("research open source video tools", "research", {})
    m = j.run(m, agent_executor(tmp_path, j.audit, run_agent=agent(
        "The request is too vague. What type of video work? Which formats?", ["skill text"])))
    assert m.status == "PAUSED" and "asking you questions" in m.steps["execute"]["why_not_verified"]


def test_repeating_the_task_back_is_not_a_finding(tmp_path):
    # Real model, 2026-11-10: the only "backed" fact was the quoted mission title.
    j = jarvis(tmp_path)
    m = j.plan("research open source video tools", "research", {})
    m = j.run(m, agent_executor(tmp_path, j.audit, run_agent=agent(
        'Memory shows a mission "research open source video tools" was done.',
        ['mission "research open source video tools" COMPLETED'])))
    assert m.status == "PAUSED"
