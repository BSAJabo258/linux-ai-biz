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
    def run(name, objective, mission_id, job=None):
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


def test_a_paused_mission_says_so_instead_of_done(tmp_path):
    # The owner's screen said "Done." after both missions came back PAUSED (2026-11-10).
    j = jarvis(tmp_path)
    mid = j.plan("research open source video tools", "research", {}).mission_id
    a = make(tmp_path, ["ok"], clients={"mission_runner": agent("What kind of video?", [])})
    out = a.t_run_mission(mid)
    assert list(out)[0] == "say" and out["say"].startswith(f"Mission {mid} is paused, not done")
    from pathlib import Path
    page = (Path(__file__).resolve().parents[1] / "src/bau/ui/jarvis.html").read_text()
    assert '(r.result && r.result.say) || "Done."' in page


def test_the_researcher_can_search_the_web_and_then_only_reads(tmp_path):
    from bau.home import shipped_data
    from bau.runtime import TOOL_SPECS, build_gateway
    gw = build_gateway(tmp_path)
    assert "search.web" in TOOL_SPECS and gw.handlers["search.web"].level == "READ_ONLY"
    assert gw.brings_outside_content("search.web")           # the run may then only read
    text = (shipped_data() / "agents" / "researcher" / "AGENT.md").read_text()
    assert "search.web" in text.split("---")[1] and "do not stop to ask" in text


# ------------------------------------------------------------ Phase 1: one controller, one job
def jobs_for(home, mission_id):
    from bau.jobs import JobStore
    return [j for j in JobStore(home).all() if j.mission_id == mission_id]


def test_a_mission_runs_through_the_executive_controller_with_one_linked_job(tmp_path):
    seen = {}

    def run(name, objective, mission_id, job=None):
        seen["job"] = job
        return RunResult("COMPLETED", "Remotion: https://github.com/remotion-dev/remotion", 2,
                         [{"capability": "memory.search", "ok": True}], 0.0, 0,
                         ["https://github.com/remotion-dev/remotion"])
    j = jarvis(tmp_path)
    m = j.plan("research open source video tools", "research", {})
    m = j.run(m, agent_executor(tmp_path, j.audit, run_agent=run))
    [job] = jobs_for(tmp_path, m.mission_id)                      # exactly one job
    assert m.status == "COMPLETED" and m.steps["execute"]["job_id"] == job.job_id
    assert seen["job"].job_id == job.job_id                        # the agent got that job
    assert job.status == "COMPLETED" and job.agent == "researcher"


def test_a_cancelled_run_ends_the_mission_cancelled_not_paused(tmp_path):
    def run(name, objective, mission_id, job=None):
        return RunResult("CANCELLED", "", 1, [], 0.0, 0, [])
    j = jarvis(tmp_path)
    m = j.plan("research", "research", {})
    m = j.run(m, agent_executor(tmp_path, j.audit, run_agent=run))
    assert m.status == "CANCELLED" and jobs_for(tmp_path, m.mission_id)[0].status == "CANCELLED"


def test_bau_mission_cancel_marks_the_running_missions_job_cancelled(tmp_path, monkeypatch):
    from bau.jarvis import cancel_mission
    from bau.jobs import JobStore
    j = jarvis(tmp_path)
    m = j.plan("research", "research", {})
    m.status = "RUNNING"
    j.save(m)
    job = JobStore(tmp_path).create(m.mission_id, m.objective, "researcher", [])
    job.status = "RUNNING"
    JobStore(tmp_path).checkpoint(job)
    out = cancel_mission(j, m.mission_id, "human:owner")
    assert out["cancelled_jobs"] == [job.job_id]
    assert JobStore(tmp_path).load(job.job_id).status == "CANCELLED"
    with pytest.raises(PermissionError):
        cancel_mission(j, m.mission_id, "jarvis")                  # only a human cancels


def test_a_mission_left_running_by_a_crash_is_paused_for_the_owner(tmp_path):
    from bau.governor import Governor
    from bau.jobs import JobStore
    j = jarvis(tmp_path)
    m = j.plan("research", "research", {})
    m.status = "RUNNING"
    j.save(m)
    job = JobStore(tmp_path).create(m.mission_id, m.objective, "researcher", [])
    job.status = "INTERRUPTED"                                     # what `bau recover` leaves
    JobStore(tmp_path).checkpoint(job)
    lone = j.plan("research again", "research", {})                # RUNNING with no job at all
    lone.status = "RUNNING"
    j.save(lone)
    Governor(tmp_path, online=True).tick(executor=None)
    for mid in (m.mission_id, lone.mission_id):
        back = jarvis(tmp_path).get(mid)
        assert back.status == "PAUSED" and "interrupted" in back.next_action
