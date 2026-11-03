"""The real jobs the autopilot runs (src/bau/autopilot.py): scan GitHub with Repo Scout and
inspect what it finds in quarantine. Nothing found is installed or run here; a repository
that passes the inspection is queued for a sandbox test, the next step. Draft jobs make the
creator's Fanvue posts while the owner's autopost is on (src/bau/creator_feed.py)."""

from __future__ import annotations

import datetime as dt
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
        if task["detail"].get("job") != "fanvue_post":
            return {"ok": False, "evidence": "no handler for this draft"}
        from .creator_feed import make_post
        try:
            return make_post(home, task)
        except Exception as e:  # noqa: BLE001 - a refused or failed picture is the evidence
            return {"ok": False, "evidence": f"{type(e).__name__}: {e}"[:300]}

    return {"scan": scan, "inspect": inspect, "research": research, "blueprint": blueprint,
            "draft": draft}


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
    from .creator_feed import fill
    return n + fill(home)                     # the creator's posts, while autopost is on
