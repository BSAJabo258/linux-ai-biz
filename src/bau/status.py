"""Mission Control status (spec §95, §106-107).

Colour meanings deliberately avoid the word "compliant" (spec §121):
GREEN = controls passed, YELLOW = human review required, ORANGE = deadline
approaching, RED = blocked / unknown / broken, BLACK = critical incident.
A red condition is never hidden to make business metrics look better.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import yaml

from .audit import AuditLog
from .home import bau_home, shipped_data
from .privacy.dsr import DSRManager
from .registry import CapabilityRegistry
from .regulations import Registry


def build_state(home: Path | None = None) -> list[dict[str, Any]]:
    local = (home or bau_home()) / "reports" / "build_state.yaml"
    src = local if local.exists() else shipped_data() / "build_state.yaml"
    return yaml.safe_load(src.read_text())


def dashboard(home: Path | None = None, on: dt.date | None = None) -> dict[str, Any]:
    home = home or bau_home()
    on = on or dt.date.today()
    items: list[dict[str, str]] = []

    def add(color: str, what: str) -> None:
        items.append({"color": color, "item": what})

    ok, msg = AuditLog(home / "audit" / "chain.jsonl").verify()
    add("GREEN" if ok else "RED", f"audit chain: {msg}")

    try:
        reg = Registry.load()
    except ValueError as e:
        add("RED", f"regulation registry invalid: {e}")
        reg = None
    if reg:
        for r in reg:
            if r.applicability(on) in ("in_force", "unknown_date") and r.is_stale(on):
                add("RED", f"{r.reg_id}: verification past due ({r['next_review']})")
            elif r.next_review and r.next_review <= on + dt.timedelta(days=30):
                add("ORANGE", f"{r.reg_id}: review due {r['next_review']}")
            if r.applicability(on) == "unknown_date":
                add("YELLOW", f"{r.reg_id}: enacted, operative date unknown")
            if r.applicability(on) in ("in_force", "unknown_date") and not r.active:
                add("YELLOW", f"{r.reg_id}: awaiting human legal sign-off ({r['bau_status']})")
        ws = home / "regulations" / ".watch-state.json"
        if ws.exists():
            import json
            for url, st in json.loads(ws.read_text()).items():
                if st.get("changed_at"):
                    stale = [rid for rid in st.get("reg_ids", []) if reg.get(rid) and
                             str(reg.get(rid)["last_verified"]) < st["changed_at"]]
                    if stale:
                        add("ORANGE", f"official source changed {st['changed_at']}: {url} "
                                      f"-> re-verify {stale}")
        for r in reg.upcoming(on, 90):
            add("ORANGE", f"{r.reg_id}: takes effect {r['effective_date']}")

    for req in DSRManager(home, AuditLog(home / "audit" / "chain.jsonl")).overdue(on):
        add("RED", f"data-rights request {req.request_id} overdue (deadline {req.deadline})")

    for p in CapabilityRegistry(home / "registry" / "capabilities.yaml").problems():
        add("RED", f"registry: {p}")

    incidents = home / "security" / "incidents.yaml"
    if incidents.exists():
        for inc in yaml.safe_load(incidents.read_text()) or []:
            if inc.get("status") != "closed":
                add("BLACK" if inc.get("severity") == "critical" else "RED",
                    f"incident {inc.get('id')}: {inc.get('title')}")

    from .governor import Governor, hold_reason
    held = hold_reason(home)
    if held:
        add("BLACK", f"governor: BAU is on HOLD ({held}) - only read-only actions run; "
                     "`bau governor release` after you have looked")
    gov_dir = home / "governor"
    if (gov_dir / "findings.jsonl").exists():
        for f in Governor(home, audit=AuditLog(home / "audit" / "chain.jsonl")
                          ).open_findings():
            if f["severity"] in ("ACTION", "CRITICAL") and not f["remedy"]:
                add("ORANGE", f"governor: {f['check']} {f['subject']}: {f['detail']}"[:300])

    for b in build_state(home):
        if b["status"] != "done":
            add("RED" if b.get("critical") else "YELLOW",
                f"build: {b['item']} [{b['status']}]")

    order = ["BLACK", "RED", "ORANGE", "YELLOW", "GREEN"]
    items.sort(key=lambda i: order.index(i["color"]))
    counts = {c: sum(1 for i in items if i["color"] == c) for c in order}
    overall = next((c for c in order if counts[c]), "GREEN")
    return {"date": on.isoformat(), "overall": overall, "counts": counts,
            "production_ready": overall == "GREEN", "items": items}
