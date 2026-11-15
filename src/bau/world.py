"""The operations world (the owner's ask, 2026-11-15: an isometric floor of robot workers, from
his three reference pictures): every robot on the screen is one of the owner's agents, and the
room it stands in comes only from its latest real job in ``jobs/``. An agent with no job sits in
the lounge; nothing walks, types or glows unless a job says so.

Read-only: it reads the agent folders, the job store and HOLD, and changes nothing.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from .home import bau_home

# Rooms on the floor (docs/visual/VISUAL_ART_DIRECTION.md), with who really works in each.
# ``hq`` is Jarvis's core; agents with no job wait in its lounge.
ROOMS = (("hq", "Headquarters", "Jarvis's core; agents with nothing to do wait in its lounge"),
         ("research", "Research library", "the researcher, and Jarvis when he researches"),
         ("forge", "The Forge", "any agent without a room of its own"),
         ("testing", "Testing lab", "Jarvis when his autopilot tests a tool in the sandbox"),
         ("innovation", "Innovation lab", "Jarvis when he scans or inspects a project"),
         ("studio", "Studio", "the producer, and Jarvis when he drafts"),
         ("finance", "Finance", "no agent works here yet"),
         ("market", "Market", "no agent works here yet"),
         ("approvals", "Waiting for you", "an agent whose job waits for your approval"),
         ("repair", "Stopped", "an agent whose job failed, was interrupted or paused"),
         ("delivery", "Delivered", "an agent whose job finished in the last 24 hours"))
# Where an agent works while its job runs; any other agent works in the Forge.
DESK = {"researcher": "research", "producer": "studio"}
LOOK = {"researcher": "researcher", "producer": "producer", "jarvis": "jarvis"}
# Jarvis's autopilot jobs (autopilot.GO) and the room each is done in.
JOB_ROOM = {"scan": "innovation", "inspect": "innovation", "blueprint": "innovation",
            "sandbox_test": "testing", "research": "research", "learn": "research",
            "draft": "studio"}
WORKING = {"PENDING", "RUNNING"}
STOPPED = {"PAUSED", "WAITING_FOR_NETWORK", "INTERRUPTED", "FAILED", "ROLLED_BACK"}
RECENT = dt.timedelta(hours=24)          # a finished job stays in its room this long
QUIET = dt.timedelta(minutes=30)         # a running job with no checkpoint this long is flagged
def _when(s: str) -> dt.datetime | None:
    try:
        t = dt.datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.UTC)


def place(name: str, job: Any, now: dt.datetime) -> tuple[str, str]:
    """(room, state) for an agent from its latest job; ``job`` None means it has none."""
    if job is None:
        return "hq", "idle"
    at = _when(job.updated_at)
    fresh = at is not None and now - at < RECENT
    if job.status in WORKING:
        return DESK.get(name, "forge"), "working"
    if job.status == "WAITING_FOR_APPROVAL":
        return "approvals", "waiting for you"
    if job.status in STOPPED:
        return "repair", job.status.lower().replace("_", " ")
    if job.status == "COMPLETED" and fresh:
        return "delivery", "done"
    return "hq", "idle"


def _agent_name(job_agent: str) -> str:
    return job_agent.removeprefix("folder:")


def world(home: Path | None = None, now: dt.datetime | None = None) -> dict[str, Any]:
    from . import agentfolders as AF
    from .governor import hold_reason
    from .jobs import JobStore
    home = home or bau_home()
    now = now or dt.datetime.now(dt.UTC)
    latest: dict[str, Any] = {}
    for job in JobStore(home).all():
        name = _agent_name(job.agent)
        old = latest.get(name)
        if old is None or (job.updated_at or "") >= (old.updated_at or ""):
            latest[name] = job
    agents = []
    names = AF.names(home)
    for name in names + sorted(set(latest) - set(names)):
        try:
            a = AF.load(name, home)
            info = {"description": a.description, "brain": a.brain, "tools": a.tools,
                    "mcp": a.mcp, "approval": AF.approval(a, home)}
        except (AF.AgentFolderError, FileNotFoundError, KeyError):
            info = {"description": "not an agent folder (a registry agent)", "brain": None,
                    "tools": [], "mcp": [], "approval": "unknown"}
        job = latest.get(name)
        room, state = place(name, job, now)
        rec: dict[str, Any] = {"name": name, **info, "room": room, "state": state,
                               "job": None}
        if job is not None:
            at = _when(job.updated_at)
            rec["job"] = {"job_id": job.job_id, "mission_id": job.mission_id,
                          "objective": job.objective[:300], "status": job.status,
                          "model": job.model, "updated_at": job.updated_at,
                          "steps_done": len(job.completed_steps),
                          "steps_left": len(job.remaining_steps),
                          "cost_usd": round(job.cost_usd, 4), "errors": job.errors[-3:],
                          "artifacts": job.artifacts[-5:], "next_action": job.next_action}
            if state == "working" and at is not None and now - at > QUIET:
                rec["quiet_minutes"] = int((now - at).total_seconds() // 60)
        rec["look"] = LOOK.get(name, "engineer")
        agents.append(rec)
    agents.insert(0, jarvis(home, now))
    held = hold_reason(home)
    counts = {r: sum(1 for a in agents if a["room"] == r) for r, _, _ in ROOMS}
    return {"rooms": [{"id": r, "name": n, "who": w} for r, n, w in ROOMS], "agents": agents,
            "hold": held, "counts": counts, "at": now.isoformat(timespec="seconds"),
            "how_to_read": "each robot is an agent; its room is its latest job's state"}


def jarvis(home: Path, now: dt.datetime) -> dict[str, Any]:
    """Jarvis himself: his autopilot's latest task (autopilot.py) puts him in the room where
    that kind of job is done; with none running he is at his core."""
    from . import autopilot
    tasks = autopilot._load(home).get("tasks", [])
    live = [t for t in tasks if t.get("state") in ("running", "waiting_owner")]
    t = max(live, key=lambda t: t.get("started") or t.get("created") or "", default=None)
    if t is None:
        ended = [t for t in tasks if t.get("state") in ("done", "failed") and t.get("finished")]
        t = max(ended, key=lambda t: t["finished"], default=None)
        if t is not None and (_when(t["finished"]) is None or now - _when(t["finished"]) > RECENT):
            t = None
    room, state = "hq", "idle"
    if t is not None:
        room, state = {"running": (JOB_ROOM.get(t["kind"], "hq"), "working"),
                       "waiting_owner": ("approvals", "waiting for you"),
                       "done": ("delivery", "done"),
                       "failed": ("repair", "failed")}[t["state"]]
    return {"name": "jarvis", "look": "jarvis", "room": room, "state": state,
            "description": "Jarvis: his autopilot works its own queue (bau autopilot)",
            "brain": "the boss model", "tools": [], "mcp": [], "approval": "built in",
            "job": None if t is None else {
                "job_id": t["id"], "mission_id": "", "objective": t.get("title", "")[:300],
                "status": t["state"].upper(), "model": None,
                "updated_at": t.get("finished") or t.get("started") or t.get("created"),
                "steps_done": 0, "steps_left": 0, "cost_usd": 0.0, "errors": [],
                "artifacts": [], "next_action": t.get("note") or None}}
