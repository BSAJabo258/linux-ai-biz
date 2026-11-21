"""The real jobs the autopilot runs (src/bau/autopilot.py): scan GitHub with Repo Scout and
inspect what it finds in quarantine. Nothing found is installed or run here; a repository
that passes the inspection gets a sandbox test plan, the next step. Draft jobs make the
creator's Fanvue posts while the owner's autopost is on (src/bau/creator_feed.py). The
``learn`` job writes a short lesson from what the autopilot actually did, and ``add_tool``
writes an adoption proposal, never an installation."""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path
from typing import Any

from . import autopilot as A


def _scout(home: Path) -> Any:
    from .audit import AuditLog
    from .scout import Scout
    return Scout(home=home, audit=AuditLog(home / "audit" / "chain.jsonl"),
                 actor="process:autopilot")


def handlers(home: Path, sc: Any = None, gh: Any = None) -> dict[str, A.Handler]:
    from .scout import watch as W
    box: dict[str, Any] = {"sc": sc, "gh": gh}

    def github() -> Any:
        box["gh"] = box["gh"] or scout().source
        return box["gh"]

    def scout() -> Any:
        box["sc"] = box["sc"] or _scout(home)
        return box["sc"]

    def scan(task: dict[str, Any]) -> dict[str, Any]:
        cat = task["detail"].get("category")
        s = scout()
        ran = W.watch(s, only=cat)
        sl = W.shortlist(s)
        picks = [i for i in sl["test_next"] if not cat or cat in i["categories"]][:5]
        info = ran["categories"].get(cat, {}) if cat else {}
        return {"ok": not ran.get("stopped"),
                "evidence": (f"{info.get('searches', 0)} searches, {len(picks)} worth a look"
                             if not ran.get("stopped") else f"GitHub stopped us: {ran['stopped']}"),
                "follow_ups": [("inspect", f"{i['repo']}: {(i['claims'] or '')[:120]}",
                                {"repo": i["repo"]}) for i in picks]}

    def inspect(task: dict[str, Any]) -> dict[str, Any]:
        c = scout().inspect(task["detail"]["repo"])
        ins = c.get("inspected", {})
        lic = c["license"].get("detected") or c["license"].get("declared")
        clean = (c["security"]["status"] == "COMMERCIAL_OK" and not ins.get("install_hooks")
                 and not ins.get("secrets"))
        follow = [("sandbox_test", task["title"],
                   {"repo": c["full_name"], "commit": ins.get("commit"), "licence": lic,
                    "security": "clean"})] if clean else []
        return {"ok": True, "evidence": (f"Sentinel: {c['security']['status']}, licence {lic}"
                                         + ("" if clean else "; not taken further")),
                "follow_ups": follow}

    def _repo_dir(repo: str) -> Path:
        return home / "scout" / "quarantine" / repo.replace("/", "__")

    def _test_command(path: Path) -> list[str]:
        """A conservative guess at the project's own test command. It is a plan, not a run."""
        if any((path / f).exists() for f in ("pyproject.toml", "setup.py", "setup.cfg",
                                             "pytest.ini", "tox.ini")) or \
                (path / "tests").is_dir():
            return ["python3", "-m", "pytest", "-q"]
        if (path / "package.json").is_file():
            return ["npm", "test"]
        if (path / "Makefile").is_file():
            return ["make", "test"]
        return []

    def sandbox_test(task: dict[str, Any]) -> dict[str, Any]:
        """Write a runnable sandbox test plan. Running untrusted code needs the owner's
        signed approval, so this job never executes it."""
        import shlex

        from .home import atomic_write_json

        repo = str(task["detail"].get("repo", ""))
        c = scout().candidates().get(repo.lower())
        if c is None or not (c.get("inspected") or {}).get("commit"):
            return {"ok": False, "evidence": "inspect the repository before planning a test"}
        if c["security"]["status"] != "COMMERCIAL_OK":
            return {"ok": False, "evidence": f"Sentinel: {c['security']['status']}"}
        path = _repo_dir(c["full_name"])
        if not path.is_dir():
            return {"ok": False, "evidence": "the quarantine copy is missing; inspect again"}
        cmd = _test_command(path)
        podman = shutil.which("podman")
        plan = {"repo": c["full_name"], "commit": c["inspected"]["commit"],
                "quarantine": str(path), "test_command": cmd, "intake_state": "QUARANTINED",
                "network": "none", "memory": "2g", "cpus": "2", "timeout_s": 900,
                "podman": podman, "approved": False, "created": A._now()}
        if cmd:
            plan["run_after_signed_approval"] = (
                f"bau sandbox {shlex.quote(str(path))} --intake-state QUARANTINED "
                f"--approved --execute -- {shlex.join(cmd)}")
        dest = home / "scout" / "test_plans" / (c["full_name"].replace("/", "__") + ".json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(dest, plan)
        A._audit(home, "sandbox_plan", "autopilot",
                 {"repo": c["full_name"], "plan": str(dest), "command": cmd,
                  "podman": bool(podman)})
        if not cmd:
            return {"ok": True, "evidence": f"test plan saved to {dest}; no test command found"}
        if not podman:
            return {"ok": True, "evidence": f"test plan saved to {dest}; podman is not installed"}
        return {"ok": True, "evidence": f"test plan ready at {dest}; signed approval still needed"}

    def add_tool(task: dict[str, Any]) -> dict[str, Any]:
        """Record an adoption proposal after the vote. Installing is a coding task for a
        human; this handler never copies, installs or enables anything."""
        from .home import atomic_write_json

        d = task.get("detail", {})
        if d.get("tested") is not True:
            return {"ok": False, "evidence": "not tested in the sandbox"}
        if d.get("security") != "clean" or not A.OK_LICENCES.match(str(d.get("licence", ""))):
            return {"ok": False, "evidence": "security or licence evidence is missing"}
        proposal = {"id": task["id"], "repo": d.get("repo"), "commit": d.get("commit"),
                    "licence": d.get("licence"), "security": d.get("security"),
                    "tested": True, "created": A._now(),
                    "status": "waiting for the owner to choose how it joins BAU",
                    "next": "a coding task: adapter, registry record or MCP server; "
                            "nothing is installed by the autopilot"}
        dest = home / "autopilot" / "proposals" / f"{task['id']}.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(dest, proposal)
        A._audit(home, "proposed", "autopilot", {"task": task["id"], "repo": d.get("repo")})
        return {"ok": True, "evidence": f"adoption proposal saved to {dest}"}

    def learn(task: dict[str, Any]) -> dict[str, Any]:
        """Write a short, honest lesson from recent autopilot work to Memory Lane."""
        from .memory import MemoryLane

        days = max(1, min(int(task.get("detail", {}).get("since_days", 7)), 90))
        since = (dt.datetime.now(dt.UTC) - dt.timedelta(days=days)).isoformat()
        tasks = A._load(home)["tasks"]
        recent = [t for t in tasks if (t.get("finished") or t.get("created", "")) >= since
                  and t["id"] != task["id"]]
        worked = [t for t in recent if t["state"] == "done"]
        trouble = [t for t in recent if t["state"] in
                   ("failed", "blocked", "vetoed", "declined")]
        if not recent:
            return {"ok": False, "evidence": f"nothing finished in the last {days} days"}
        lines = [f"Autopilot, last {days} days: {len(worked)} done, {len(trouble)} to review.",
                 "", "## Worked"]
        lines += [f"- {t['title']}" + (f": {t['note']}" if t.get("note") else "")
                  for t in worked[:10]] or ["- nothing finished"]
        lines += ["", "## To review"]
        lines += [f"- {t['title']} ({t['state']})" + (f": {t['note']}" if t.get("note")
                                                      else "") for t in trouble[:10]] or \
                 ["- nothing failed, blocked or vetoed"]
        lines += ["", "## Next time",
                  "- Repeat the steps that left evidence; keep the audit event.",
                  "- A blocked job needs a handler, not a retry.",
                  "- A vetoed job stays stopped unless the owner changes the compass."]
        rec = MemoryLane(home).add("lesson", f"Autopilot review, last {days} days",
                                   "\n".join(lines)[:6000], tags=["autopilot", "lesson"],
                                   source="autopilot")
        A._audit(home, "learned", "autopilot", {"record": rec.id, "done": len(worked),
                                                "review": len(trouble)})
        return {"ok": True, "evidence": f"lesson {rec.id}: {len(worked)} done, "
                                        f"{len(trouble)} to review"}

    def research(task: dict[str, Any]) -> dict[str, Any]:
        """What the owner pointed Jarvis at: search GitHub, read the top blueprints."""
        run = scout().find(task["detail"]["query"], max_queries=2, per_query=10, readmes=1)
        top = [r["id"] for r in run.get("ranked", [])][:3]          # id: owner/repo
        return {"ok": bool(top) or not run.get("searches"),
                "evidence": f"{run.get('found', 0)} found; reading {len(top)} blueprints",
                "follow_ups": [("blueprint", f"blueprint {n}", {"repo": n}) for n in top]}

    def blueprint(task: dict[str, Any]) -> dict[str, Any]:
        from . import blueprint as B
        bp = B.read(home, task["detail"]["repo"], github())
        return {"ok": True, "evidence": B.summary(bp).split("\n")[1]}

    def draft(task: dict[str, Any]) -> dict[str, Any]:
        job = task["detail"].get("job")
        if job not in ("fanvue_post", "fanvue_clip"):
            return {"ok": False, "evidence": "no handler for this draft"}
        from .creator_feed import make_clip, make_post
        try:
            return (make_clip if job == "fanvue_clip" else make_post)(home, task)
        except Exception as e:  # noqa: BLE001 - a refused or failed picture is the evidence
            return {"ok": False, "evidence": f"{type(e).__name__}: {e}"[:300]}

    def workstation_shift(task: dict[str, Any]) -> dict[str, Any]:
        """Run the productivity manager's approved internal work. This is the workstation's
        own shift: no per-item confirmation card. External effects still stop at the gateway."""
        from . import workstation as W
        from .audit import AuditLog
        n = max(1, min(int(task.get("detail", {}).get("max_tasks", 1)), 3))
        out = W.run_shift(home, audit=AuditLog(home / "audit" / "chain.jsonl"),
                          max_tasks=n, by="process:autopilot")
        ran = out.get("ran") or []
        if not ran:
            return {"ok": True, "evidence": "no manager-approved workstation work was waiting"}
        ok = all(r.get("status") == "done" for r in ran)
        text = "; ".join(f"{r['role']}: {r['status']}" for r in ran)
        return {"ok": ok, "evidence": f"workstation shift: {text}"}

    return {"scan": scan, "inspect": inspect, "sandbox_test": sandbox_test,
            "add_tool": add_tool, "learn": learn, "research": research,
            "blueprint": blueprint, "draft": draft, "workstation": workstation_shift}


def seed(home: Path, days: int = 7) -> int:
    """Keep growing: a scan for every watched category not scanned in the last week."""
    from .scout import watch as W
    since = (dt.datetime.now(dt.UTC) - dt.timedelta(days=days)).isoformat()
    tasks = A._load(home)["tasks"]
    n = 0
    for key, c in W.load()["categories"].items():
        recent = any(t["kind"] == "scan" and t["detail"].get("category") == key and
                     (t["state"] in ("queued", "running") or t.get("finished", "") >= since)
                     for t in tasks)
        if not recent and A.add(home, "scan", f"scan {c['title']}", {"category": key},
                                source="autopilot (weekly)"):
            n += 1
    recent_lesson = any(
        t["kind"] == "learn" and
        (t["state"] in ("queued", "running", "waiting_owner") or
         (t.get("finished") or "") >= since)
        for t in tasks)
    worked = any(t["state"] in ("done", "failed", "blocked", "vetoed", "declined") and
                 (t.get("finished") or t.get("created", "")) >= since for t in tasks)
    if not recent_lesson and worked and A.add(
            home, "learn", "review what the autopilot did",
            {"since_days": days}, source="autopilot (weekly)"):
        n += 1
    from . import departments
    from . import workstation as W
    try:
        departments.due(home)              # each department's daily standing work
    except Exception:  # noqa: BLE001 - the rest of the autopilot's work goes on
        pass
    # A shift whenever work waits (it was at most one a week, one task each: the departments
    # stood still, 2026-11-20). A.add never queues a second open shift.
    if W.queued(home):
        if A.add(home, "workstation", "run the workstation shift", {"max_tasks": 3},
                 source="autopilot (workstation)"):
            n += 1
    from .creator_feed import fill
    return n + fill(home)                     # the creator's posts, while autopost is on
