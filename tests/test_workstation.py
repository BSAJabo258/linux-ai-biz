"""The AI workstation: real job logs move health, a zero-health worker retires, and a
successor inherits its open work. The productivity manager can approve only low-risk
internal work; the gateway's human gates still apply."""

from bau import agentfolders as AF
from bau import workstation as W
from bau.jobs import JobStore


def home(tmp_path, role="producer", approved=True):
    if approved:
        AF.approve(role, "human:owner", tmp_path)
    return tmp_path


def job(home, status="COMPLETED", objective="draft a caption", role="producer",
        verification="VERIFIED"):
    store = JobStore(home)
    j = store.create("m1", objective, f"folder:{role}", ["step-1"])
    j.status = status
    j.verification = verification if status == "COMPLETED" else "UNCHECKED"
    j.remaining_steps = ["step-1"] if status != "COMPLETED" else []
    store.checkpoint(j)
    return j


def test_a_good_delivery_raises_health_and_shows_a_drop_off(tmp_path):
    h = home(tmp_path)
    j = job(h)
    st = W.refresh(h)
    w = st["workers"][0]
    assert w["role"] == "producer" and w["health"] == 100
    assert w["stats"]["delivered"] == 1
    assert any(e["kind"] == "delivered" and e["job"] == j.job_id for e in st["events"])
    assert W.view_from(st, h)["workers"][0]["status"] == "delivering"


def test_four_bad_jobs_retire_the_worker_and_spawn_a_successor_with_the_logs(tmp_path):
    h = home(tmp_path)
    for i in range(4):
        job(h, status="FAILED", objective=f"bad work {i}")
    st = W.refresh(h)
    assert "producer:2" in [w["id"] for w in st["workers"]]
    dead = st["graveyard"][-1]
    assert dead["id"] == "producer:1" and dead["cause"] == "health reached zero"
    successor = next(w for w in st["workers"] if w["role"] == "producer")
    assert successor["generation"] == 2 and successor["health"] == 80
    assert successor["inherited"]["from"] == "producer:1"
    assert successor["inherited"]["tasks"] == 4
    assert sum("work failed" in line for line in successor["inherited"]["logs"]) == 4
    assert any(e["kind"] == "spawned" and e["worker_id"] == "producer:2"
               for e in st["events"])


def test_the_manager_approves_low_risk_work_and_vetoes_outside_effects(tmp_path):
    h = home(tmp_path)
    W.refresh(h)
    good = W.assign(h, "producer", "draft the next caption from the log", "human:owner")
    assert good["status"] == "approved" and good["manager"]["approved"] is True
    bad = W.assign(h, "producer", "post this to Fanvue", "human:owner")
    assert bad["status"] == "waiting_owner" and "outside effect" in bad["manager"]["reason"]
    no_popup = W.view(h)
    assert all(t["state"] != "pending" for t in no_popup["tasks"])


def test_an_unapproved_agent_cannot_be_started_by_the_manager(tmp_path):
    h = home(tmp_path, approved=False)
    W.refresh(h)
    t = W.assign(h, "producer", "review the log", "human:owner")
    assert t["status"] == "waiting_owner"
    assert "approve producer" in t["manager"]["reason"]


def test_a_shift_runs_approved_work_with_no_confirm_card(tmp_path):
    h = home(tmp_path)
    W.refresh(h)
    t = W.assign(h, "producer", "review the latest log", "human:owner")
    seen = []

    class Result:                       # answers with a fact its tool really returned
        status = "COMPLETED"
        final_text = 'Reviewed: "error 504 at 10:42" in the latest log'
        steps, cost_usd, injection_flags = 1, 0.0, 0
        tool_calls = [{"capability": "memory.brain", "ok": True}]
        evidence = ["latest log: error 504 at 10:42"]

    out = W.run_shift(h, runner=lambda role, objective, mission_id, job: (
        seen.append((role, objective)) or Result()), max_tasks=1)
    assert seen == [("producer", "review the latest log")]
    assert out["ran"][0]["status"] == "done"
    assert all(x["id"] != t["id"] for x in out["tasks"])       # finished work leaves the floor


def test_autopilot_shift_is_queued_only_when_manager_work_waits(tmp_path):
    from bau import autopilot as A
    from bau import autopilot_jobs as J
    h = home(tmp_path)
    J.seed(h)
    assert not any(t["kind"] == "workstation" for t in A._load(h)["tasks"])
    t = W.assign(h, "producer", "review the latest log", "human:owner")
    assert t["status"] == "approved"
    assert J.seed(h) >= 1
    assert any(t["kind"] == "workstation" for t in A._load(h)["tasks"])
