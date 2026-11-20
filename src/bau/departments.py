"""The departments' standing work: each approved agent gets its daily task in its workstation
inbox (src/bau/data/departments.yaml), and the autopilot's shifts run it (docs/WORKSTATION.md).

Nothing here approves anything: the owner approves each agent folder, and the productivity
manager (workstation.manager_review) reviews every task as before."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import yaml

from .home import shipped_data


def standing() -> list[dict[str, Any]]:
    return yaml.safe_load((shipped_data() / "departments.yaml").read_text()) or []


def due(home: Path, now: dt.datetime | None = None) -> list[dict[str, Any]]:
    """Put each department's standing task in its inbox when it is due. Returns the tasks."""
    from . import workstation as W
    now = now or dt.datetime.now(dt.UTC)
    st = W.refresh(home)
    made = []
    for d in standing():
        if W._approval(d["role"], home)[0] != "approved":
            continue                       # the owner's approval card comes first
        mine = [t for t in st["tasks"] if t["role"] == d["role"]
                and t.get("source", "").endswith("(standing)")]
        if any(t["status"] in W.OPEN for t in mine):
            continue                       # one at a time
        last = max((t["created"] for t in mine), default="")
        if last and now - dt.datetime.fromisoformat(last) < dt.timedelta(
                hours=float(d.get("every_hours", 24))):
            continue
        try:
            made.append(W.assign(home, d["role"], d["objective"], "process:autopilot",
                                 kind=d["kind"], source_note="(standing)"))
        except (KeyError, ValueError):
            continue                       # no worker for it yet
        st = W.refresh(home)
    return made
