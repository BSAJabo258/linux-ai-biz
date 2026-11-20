"""The world shows a real task's whole life (the owner's world spec, 2026-11-19): recorded and
assigned at Headquarters, dispatched to her desk, working, the result, the manager's check,
your review, delivered. Every step is read from the job and its mission, never a timer."""

import datetime as dt

from bau import agentfolders as AF
from bau.jobs import JobStore
from bau.store import JsonlStore
from bau.world import lifecycle, place, world

NOW = dt.datetime.now(dt.UTC)


def job(home, status, verification="UNCHECKED", mission="msn_1", tools=()):
    store = JobStore(home)
    j = store.create(mission, "find two soy wax suppliers", "folder:researcher", ["step-1"])
    j.status, j.verification, j.tools = status, verification, list(tools)
    j.remaining_steps = [] if status == "COMPLETED" else ["step-1"]
    if status == "COMPLETED" and verification == "FAILED":
        j.next_action = "the owner reviews it: 1 fact(s) no tool result backs: 99,000"
    store.checkpoint(j)
    return j


def steps(j, mission=None):
    return {s["step"]: s["state"] for s in lifecycle(j, mission)}


def test_recorded_but_not_started_is_assigned_at_headquarters(tmp_path):
    j = job(tmp_path, "PENDING")
    assert place("researcher", j, NOW) == ("hq", "assigned")
    assert steps(j) == {"Recorded": "done", "Dispatched": "now"}


def test_started_she_walks_to_her_desk_and_works(tmp_path):
    j = job(tmp_path, "RUNNING")
    assert place("researcher", j, NOW) == ("research", "working")
    assert steps(j) == {"Recorded": "done", "Dispatched": "done", "Working": "now"}


def test_checked_and_delivered(tmp_path):
    j = job(tmp_path, "COMPLETED", "VERIFIED", tools=["search.web"])
    assert place("researcher", j, NOW) == ("delivery", "done")
    s = steps(j, {"status": "COMPLETED"})
    assert s == {"Recorded": "done", "Dispatched": "done", "Working": "done", "Result": "done",
                 "Checked (manager)": "done", "Your review": "not needed", "Delivered": "done"}
    assert "search.web" in next(x["detail"] for x in lifecycle(j, None) if x["step"] == "Result")


def test_a_failed_check_waits_for_your_review_and_is_not_delivered(tmp_path):
    j = job(tmp_path, "COMPLETED", "FAILED")
    assert place("researcher", j, NOW) == ("approvals", "waiting for you")
    s = steps(j, {"status": "PAUSED"})
    assert s["Checked (manager)"] == "stopped" and s["Your review"] == "waiting"
    assert s["Delivered"] == "waiting"
    checked = next(x for x in lifecycle(j, None) if x["step"] == "Checked (manager)")
    assert "99,000" in checked["detail"]


def test_a_failed_job_stops_and_says_why(tmp_path):
    j = job(tmp_path, "FAILED")
    j.errors = ["RuntimeError: the agent did not run"]
    s = steps(j)
    assert place("researcher", j, NOW)[0] == "repair"
    assert s["Working"] == "done" and s["Result"] == "stopped" and s["Delivered"] == "stopped"


def test_the_world_carries_the_steps_and_lists_assigned_tasks(tmp_path):
    AF.approve("researcher", "human:owner", tmp_path)
    j = job(tmp_path, "PENDING")
    JsonlStore(tmp_path / "jobs" / "missions.jsonl").append(
        {"mission_id": "msn_1", "status": "READY"})
    w = world(tmp_path)
    r = next(a for a in w["agents"] if a["name"] == "researcher")
    assert r["state"] == "assigned" and r["job"]["job_id"] == j.job_id
    assert [x["step"] for x in r["job"]["lifecycle"]] == ["Recorded", "Dispatched"]
    assert any(t["agent"] == "researcher" and t["state"] == "assigned" for t in w["tasks"])
