"""COMPLETED, VERIFIED and APPROVED are three different things (the owner, 2026-11-18: "These must
never be interchangeable"). Found: a job read COMPLETED while its mission's fact check had
failed, so the operations world showed it as Delivered and the workstation paid its worker for
it; and a workstation shift ran its agent without the mission's check at all."""

import datetime as dt
import json
from types import SimpleNamespace

import pytest
from test_mission_run import agent, jarvis

from bau import agentfolders as AF
from bau import workstation as W
from bau.jarvis import agent_executor
from bau.jobs import JobStore
from bau.world import place

BACKED = ("Remotion has 21,000 stars: https://github.com/remotion-dev/remotion",
          ["remotion-dev/remotion stars 21,000 https://github.com/remotion-dev/remotion"])
UNBACKED = ("Remotion has 99,000 stars: https://github.com/remotion-dev/remotion",
            ["remotion-dev/remotion stars 21,000"])


def run_mission(home, text, evidence):
    j = jarvis(home)
    m = j.plan("research open source video tools", "research", {})
    m = j.run(m, agent_executor(home, j.audit, run_agent=agent(text, evidence)))
    return m, JobStore(home).load(m.steps["execute"]["job_id"])


def test_a_checked_result_is_completed_and_verified_with_its_tools(tmp_path):
    m, job = run_mission(tmp_path, *BACKED)
    assert m.status == "COMPLETED"
    assert job.status == "COMPLETED" and job.verification == "VERIFIED"
    assert job.tools == ["memory.search"] and job.approvals == []      # APPROVED is apart
    assert place("researcher", job, dt.datetime.now(dt.UTC)) == ("delivery", "done")


def test_a_failed_check_is_completed_but_never_delivered(tmp_path):
    m, job = run_mission(tmp_path, *UNBACKED)
    assert m.status == "PAUSED"
    assert job.status == "COMPLETED" and job.verification == "FAILED"     # finished, unchecked
    assert "owner reviews it" in job.next_action and "99,000" in job.next_action
    assert place("researcher", job, dt.datetime.now(dt.UTC)) == ("approvals", "waiting for you")


def test_the_workstation_pays_only_for_verified_work(tmp_path):
    AF.approve("researcher", "human:owner", tmp_path)
    run_mission(tmp_path, *UNBACKED)
    w = next(x for x in W.refresh(tmp_path)["workers"] if x["role"] == "researcher")
    assert w["stats"]["delivered"] == 0 and w["health"] < W.START_HEALTH
    run_mission(tmp_path, *BACKED)
    w = next(x for x in W.refresh(tmp_path)["workers"] if x["role"] == "researcher")
    assert w["stats"]["delivered"] == 1


def test_a_finished_but_unchecked_job_earns_nothing(tmp_path):
    AF.approve("producer", "human:owner", tmp_path)
    store = JobStore(tmp_path)
    j = store.create("m1", "draft a caption", "folder:producer", [])
    j.status = "COMPLETED"                          # never went through the check
    store.checkpoint(j)
    w = next(x for x in W.refresh(tmp_path)["workers"] if x["role"] == "producer")
    assert w["stats"]["delivered"] == 0 and w["health"] == W.START_HEALTH


def test_a_shift_goes_through_the_mission_check_and_waits_for_review(tmp_path):
    AF.approve("producer", "human:owner", tmp_path)
    W.refresh(tmp_path)
    t = W.assign(tmp_path, "producer", "draft three caption ideas", "human:owner", kind="draft")
    assert t["status"] == "approved"

    def unchecked(role, objective, mission_id, job):     # a draft with no fact a tool backs
        return SimpleNamespace(status="COMPLETED", final_text="Here are three ideas.",
                               steps=1, cost_usd=0.0, injection_flags=0,
                               tool_calls=[{"capability": "artifact.write_draft", "ok": True}],
                               evidence=['{"saved": "artifacts/drafts/ideas.md"}'])
    out = W.run_shift(tmp_path, runner=unchecked)
    assert out["ran"][0]["status"] == "review"
    job = JobStore(tmp_path).load(next(x for x in W.refresh(tmp_path)["tasks"]
                                       if x["id"] == t["id"])["source_job"])
    assert job.verification == "FAILED" and job.mission_id == f"workstation:{t['id']}"
    again = W.run_shift(tmp_path, runner=unchecked)       # never run again by itself
    assert again["ran"] == []


def test_a_job_record_cannot_hold_a_made_up_verification(tmp_path):
    store = JobStore(tmp_path)
    j = store.create("m1", "x", "folder:producer", [])
    j.verification = "PROBABLY"
    with pytest.raises(ValueError):
        store.checkpoint(j)


def test_jobs_written_before_the_change_read_as_unchecked(tmp_path):
    store = JobStore(tmp_path)
    j = store.create("m1", "x", "folder:producer", [])
    p = store.dir / f"{j.job_id}.json"
    old = json.loads(p.read_text())
    old.pop("verification")
    p.write_text(json.dumps(old))
    assert store.load(j.job_id).verification == "UNCHECKED"
