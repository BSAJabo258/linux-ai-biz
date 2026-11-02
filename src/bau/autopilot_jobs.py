"""The real jobs the autopilot runs (src/bau/autopilot.py): scan GitHub with Repo Scout and
inspect what it finds in quarantine. Nothing found is installed or run here; a repository
that passes the inspection is queued for a sandbox test, the next step."""

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


def handlers(home: Path, sc: Any = None) -> dict[str, A.Handler]:
    from .scout import watch as W
    box: dict[str, Any] = {"sc": sc}

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

    return {"scan": scan, "inspect": inspect}


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
    return n
