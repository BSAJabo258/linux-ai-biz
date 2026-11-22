"""The AI workstation, life and death: workers' health comes from real job logs, a worker at zero
retires and a successor inherits its open work, and the productivity manager can approve
only low-risk internal work (everything with an outside effect keeps the owner's approval).
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from bau import agentfolders as AF
from bau import workstation as W
from bau.audit import AuditLog


@pytest.fixture
def home(tmp_path):
    AF.new("helper", tmp_path, "producer")
    return tmp_path


def approve(home):
    AF.approve("helper", "human:owner", home, AuditLog(home / "audit" / "chain.jsonl"))


# A shift runs the same path as a mission (jarvis.run_checked): its result must pass the same
# check, so a good stand-in answers with a fact its tool really returned.
def ok(role, objective, mission_id, job):
    return SimpleNamespace(status="COMPLETED", final_text="Saved: https://example.com/caption-1",
                           steps=1, cost_usd=0.0, injection_flags=0,
                           tool_calls=[{"capability": "artifact.write_draft", "ok": True}],
                           evidence=['{"saved": "https://example.com/caption-1"}'])


def bad(role, objective, mission_id, job):
    return SimpleNamespace(status="FAILED", final_text="it broke", steps=1, cost_usd=0.0,
                           injection_flags=0, tool_calls=[], evidence=[])


def test_a_worker_clocks_in_for_each_agent_folder(home):
    v = W.view(home)
    helper = next(w for w in v["workers"] if w["role"] == "helper")
    assert helper["health"] == W.START_HEALTH and helper["generation"] == 1
    assert {w["role"] for w in v["workers"]} == set(AF.names(home))
    assert any(e["kind"] == "hired" for e in v["events"])


@pytest.mark.parametrize("objective", [
    "post the new picture to Fanvue", "pay the hosting bill", "send an email to the list",
    "delete the old drafts", "install a new tool"])
def test_the_manager_never_approves_an_outside_effect(home, objective):
    approve(home)
    t = W.assign(home, "helper", objective, "human:owner", kind="draft")
    assert t["status"] == "waiting_owner" and not t["manager"]["approved"]


def test_the_manager_approves_low_risk_work_and_the_shift_runs_it(home):
    approve(home)
    t = W.assign(home, "helper", "draft three caption ideas", "human:owner", kind="draft")
    assert t["status"] == "approved"
    r = W.run_shift(home, runner=ok)
    assert r["ran"][0]["status"] == "done"
    assert any(e["kind"] == "delivered" for e in r["events"])


def test_only_the_owner_or_the_autopilot_assigns_and_runs(home):
    with pytest.raises(PermissionError):
        W.assign(home, "helper", "draft something", "agent:jarvis")
    with pytest.raises(PermissionError):
        W.run_shift(home, runner=ok, by="agent:jarvis")


def test_a_parked_task_goes_on_once_the_owner_approves_the_folder(home):
    t = W.assign(home, "helper", "research three competitors", "human:owner",
                 kind="research")
    assert t["status"] == "waiting_owner" and "agent folder" in t["manager"]["reason"]
    approve(home)
    st = W.refresh(home)
    assert next(x for x in st["tasks"] if x["id"] == t["id"])["status"] == "approved"


def helper(st):
    return next(w for w in st["workers"] if w["role"] == "helper")


def _fail_a_job(home):
    from bau.jobs import JobStore
    store = JobStore(home)
    j = store.create("m1", "draft a caption", "folder:helper", ["step-1"])
    j.status = "FAILED"
    store.checkpoint(j)


def _set_health(home, n):
    st = W.refresh(home)
    helper(st)["health"] = n
    W._save(home, st)


def test_a_worker_that_keeps_failing_dies_and_its_successor_inherits(home):
    approve(home)
    for _ in range(3):
        W.assign(home, "helper", "draft a caption", "human:owner", kind="draft")
        W.run_shift(home, runner=bad)
    assert helper(W.refresh(home))["health"] == 25          # 3 failed jobs at -25 each
    _set_health(home, 10)
    t = W.assign(home, "helper", "draft one more caption", "human:owner", kind="draft")
    assert t["status"] == "waiting_owner" and "health" in t["manager"]["reason"]
    _fail_a_job(home)                                        # one more failure: 10 - 25
    v = W.view_from(W.refresh(home), home)
    assert v["graveyard"] and v["graveyard"][0]["id"] == "helper:1"
    heir = helper(v)
    assert heir["id"] == "helper:2" and heir["health"] <= W.SUCCESSOR_HEALTH
    assert heir["inherited"]["from"] == "helper:1" and heir["inherited"]["logs"]
    left = next(x for x in v["tasks"] if x["id"] == t["id"])
    assert left["inherited_from"] == "helper:1" and left["state"] == "approved"
    kinds = [e["kind"] for e in v["events"]]
    assert "died" in kinds and "spawned" in kinds


def test_a_resting_worker_gets_its_health_back_and_its_held_work_goes_on(home):
    """Found 2026-11-21: "rest first" never gave health back, the held task had no card and
    was never looked at again, and the worker faded to 0 and died."""
    approve(home)
    _set_health(home, 10)
    t = W.assign(home, "helper", "draft one more caption", "human:owner", kind="draft")
    assert t["status"] == "waiting_owner"
    st = W.refresh(home, now=dt.datetime.now(dt.UTC) + dt.timedelta(days=4))
    assert helper(st)["health"] == W.LOW_HEALTH and not st["graveyard"]
    assert next(x for x in st["tasks"] if x["id"] == t["id"])["status"] == "approved"


def test_idle_workers_lose_health_by_the_day_but_waiting_never_kills(home):
    approve(home)
    W.refresh(home)
    st = W.refresh(home, now=dt.datetime.now(dt.UTC) + dt.timedelta(days=5))
    assert helper(st)["health"] == W.START_HEALTH - 5 * W.IDLE_DECAY_PER_DAY
    st = W.refresh(home, now=dt.datetime.now(dt.UTC) + dt.timedelta(days=60))
    assert helper(st)["health"] == W.LOW_HEALTH and not st["graveyard"]


def test_a_worker_waiting_for_the_owners_approval_does_not_fade(home):
    W.refresh(home)                                          # folder not approved yet
    st = W.refresh(home, now=dt.datetime.now(dt.UTC) + dt.timedelta(days=60))
    assert helper(st)["health"] == W.START_HEALTH and not st["graveyard"]


@pytest.mark.parametrize("status,kind", [("FAILED", "retry"), ("PAUSED", "continue"),
                                         ("CANCELLED", None), ("WAITING_FOR_APPROVAL", None)])
def test_only_failed_or_interrupted_jobs_come_back_as_work(home, status, kind):
    from bau.jobs import JobStore
    store = JobStore(home)
    j = store.create("m1", "draft a caption", "folder:helper", ["step-1"])
    j.status = status
    store.checkpoint(j)
    st = W.refresh(home)
    made = [t for t in st["tasks"] if t.get("source_job") == j.job_id]
    assert [t["kind"] for t in made] == ([kind] if kind else [])   # the owner's cancel holds

