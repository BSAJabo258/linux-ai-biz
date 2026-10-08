"""What the Jarvis screen shows around the core: one node per part of the business.

Every node is built from data BAU already keeps (the same read tools Jarvis uses), so the
screen never shows a status nobody measured. A source that fails shows as "bad" with its
error - never as green. States: ok | warn | bad | idle (nothing yet) | off (not connected).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _safe(fn, *a: Any) -> tuple[Any, str | None]:
    try:
        return fn(*a), None
    except Exception as e:  # one broken source must not blank the screen
        return None, f"{type(e).__name__}: {e}"[:200]


def _node(nid: str, label: str, group: str, state: str, summary: str,
          detail: Any = None, ask: str | None = None, **extra: Any) -> dict[str, Any]:
    return {"id": nid, "label": label, "group": group, "state": state, "summary": summary,
            "detail": detail, "ask": ask, **extra}


def _broken(nid: str, label: str, group: str, err: str) -> dict[str, Any]:
    return _node(nid, label, group, "bad", "could not read: " + err, {"error": err})


def episodes(home: Path) -> list[dict[str, Any]]:
    """Every episode with its stages and the one thing that can happen next."""
    from . import workspace as W
    out = []
    base = W.root(home)
    for ws in sorted(base.iterdir()) if base.is_dir() else []:
        if not (ws / "CLAUDE.md").exists():
            continue
        for ep in W.episodes(ws):
            rows = W.status(ws, ep)
            nxt = None
            for r in rows:
                if r["state"].startswith("drafted"):
                    nxt = {"action": "check", "stage": r["stage"][:2], "issues": r["issues"]}
                    break
                if r["state"] == "ready":
                    nxt = {"action": "draft", "stage": r["stage"][:2]}
                    break
                if r["state"] == "yours to do":
                    nxt = {"action": "owner", "stage": r["stage"][:2]}
                    break
            out.append({"workspace": ws.name, "episode": ep.name,
                        "stages": [{"stage": r["stage"], "state": r["state"],
                                    "issues": r["issues"]} for r in rows],
                        "next": nxt})
    return out


def _models(home: Path, active: dict[str, Any]) -> dict[str, Any]:
    from .registry import CapabilityRegistry
    reg = CapabilityRegistry(home / "registry" / "capabilities.yaml")
    backups = list(active.get("fallbacks") or [])
    rows = []
    for mid, rec in sorted(reg.data["model"].items()):
        bench = rec.get("benchmark") or {}
        rows.append({"model": mid, "status": rec.get("status"),
                     "where": rec.get("deployment"),
                     "role": "first" if mid == active.get("id") else
                             "backup" if mid in backups else "",
                     "tested": bool(bench.get("reply_ok")) if bench else None})
    return {"active": active.get("id"), "backups": backups, "models": rows}


def overview(asst: Any) -> dict[str, Any]:
    """The nodes for the Jarvis screen. ``asst`` is the running Assistant."""
    from .audit import AuditLog
    from .governor import hold_reason
    home: Path = asst.home
    nodes: list[dict[str, Any]] = []
    hold = hold_reason(home)

    # ---------------------------------------------------------------- the team
    night, err = _safe(asst.t_night)
    if err:
        nodes.append(_broken("chief", "Chief of staff", "team", err))
    else:
        needs = len(night["needs_you"])
        state = "bad" if night["hold"] else "warn" if needs else "ok"
        nodes.append(_node("chief", "Chief of staff", "team", state,
                           f"on HOLD: {night['hold']}" if night["hold"] else
                           f"{needs} thing(s) need you" if needs else "nothing needs you",
                           night, "Give me my briefing."))

    eps, err = _safe(episodes, home)
    if err:
        nodes.append(_broken("producer", "Producer", "team", err))
    else:
        waiting = sum(1 for e in eps if e["next"] and e["next"]["action"] == "check")
        flagged = sum(1 for e in eps for s in e["stages"] if s["issues"])
        state = ("idle" if not eps else "bad" if flagged else "warn" if waiting else "ok")
        nodes.append(_node("producer", "Producer", "team", state,
                           "no episodes yet" if not eps else
                           f"{len(eps)} episode(s), {waiting} waiting for your check",
                           {"episodes": eps}, "Where are my episodes?"))

    q, err = _safe(asst.t_publish_queue)
    if err:
        nodes.append(_broken("publisher", "Publisher", "team", err))
    else:
        q = [i for i in q if isinstance(i, dict) and i.get("item_id")]
        nodes.append(_node("publisher", "Publisher", "team", "warn" if q else "idle",
                           f"{len(q)} video(s) waiting for you" if q else "queue empty",
                           q, "What's in the publishing queue?"))

    ms, err = _safe(asst.t_missions)
    if err:
        nodes.append(_broken("strategist", "Strategist", "team", err))
    else:
        review = [m for m in ms if m["status"] == "NEEDS_REVIEW"]
        nodes.append(_node("strategist", "Strategist", "team",
                           "warn" if review else "ok" if ms else "idle",
                           f"{len(ms)} mission(s), {len(review)} need your sign-off"
                           if ms else "no missions yet", ms, "What missions are open?"))

    gaps, err = _safe(asst.t_brain_gaps)
    if err:
        nodes.append(_broken("researcher", "Researcher", "team", err))
    else:
        nodes.append(_node("researcher", "Researcher", "team", "warn" if gaps else "ok",
                           f"{len(gaps)} gap(s) in how the business is written down"
                           if gaps else "no known gaps", gaps,
                           "What isn't automatable yet?"))

    dl, err = _safe(asst.t_deadlines)
    if err:
        nodes.append(_broken("compliance", "Compliance", "team", err))
    else:
        n = sum(len(dl[k]) for k in ("legal_review_open", "regulation_reviews_due",
                                     "incidents_open"))
        nodes.append(_node("compliance", "Compliance", "team", "warn" if n else "ok",
                           f"{n} review(s) or incident(s) open" if n else
                           "no reviews due in 14 days", dl, "Any deadlines coming up?"))

    money, err = _safe(asst.t_money)
    if err:
        nodes.append(_broken("finance", "Finance", "team", err))
    else:
        has = any(money.get(k) for k in ("revenue", "costs_by_kind"))
        nodes.append(_node("finance", "Finance", "team", "ok" if has else "idle",
                           f"revenue {money.get('revenue', 0)} in {money['days']} days"
                           if has else "no money recorded yet", money,
                           "How's the money looking?"))

    st, err = _safe(asst.t_status)
    if err:
        nodes.append(_broken("watchdog", "Watchdog", "team", err))
    else:
        colour = {"GREEN": "ok", "YELLOW": "warn", "ORANGE": "warn"}.get(st["overall"], "bad")
        nodes.append(_node("watchdog", "Watchdog", "team", "bad" if hold else colour,
                           f"overall {st['overall']}" + (f", {st['setup_steps_left']} setup "
                                                         "step(s) left"
                                                         if st["setup_steps_left"] else ""),
                           st, "What's the system status?"))

    # ---------------------------------------------------------------- systems
    mdl, err = _safe(_models, home, asst.model or {})
    if err:
        nodes.append(_broken("models", "Models", "system", err))
    else:
        nodes.append(_node("models", "Models", "system", "ok" if asst.provider else "bad",
                           f"thinking with {asst.model_summary()}" if asst.provider else
                           "no approved model: Jarvis runs in plain mode", mdl))

    def memory() -> dict[str, Any]:
        from .brain import Brain
        from .memory import MemoryLane
        recent = MemoryLane(home).recent(8)
        return {"brain_notes": len(Brain(home).notes()),
                "recent_memories": [f"{r.title}" for r in recent]}
    mem, err = _safe(memory)
    if err:
        nodes.append(_broken("memory", "Memory", "system", err))
    else:
        nodes.append(_node("memory", "Memory", "system",
                           "ok" if mem["brain_notes"] or mem["recent_memories"] else "idle",
                           f"{mem['brain_notes']} brain note(s), "
                           f"{len(mem['recent_memories'])} recent memory(ies)", mem,
                           "What do you remember?"))

    def audit() -> dict[str, Any]:
        log = AuditLog(home / "audit" / "chain.jsonl")
        ok, msg = log.verify()
        recs = list(log.records())
        return {"intact": ok, "check": msg, "records": len(recs),
                "latest": [f"{r.get('ts', '')[:16]} {r.get('event')} by {r.get('actor')}"
                           for r in recs[-10:]][::-1]}
    au, err = _safe(audit)
    if err:
        nodes.append(_broken("audit", "Audit", "system", err))
    else:
        nodes.append(_node("audit", "Audit", "system", "ok" if au["intact"] else "bad",
                           f"{au['records']} record(s), chain intact" if au["intact"]
                           else "chain check FAILED: " + au["check"], au))

    # ---------------------------------------------------------------- connections
    for nid, label in (("youtube", "YouTube"), ("tiktok", "TikTok")):
        signed = (home / "secrets" / f"{nid}.json").exists()
        nodes.append(_node(nid, label, "connector", "ok" if signed else "off",
                           "signed in" if signed else f"not signed in: bau {nid} login"))
    for nid, label in (("email", "Email"), ("drive", "Drive"), ("calendar", "Calendar"),
                       ("crm", "CRM")):
        nodes.append(_node(nid, label, "connector", "off",
                           "not connected yet: each connection is added one at a time, "
                           "read-only first"))

    return {"hold": hold, "nodes": nodes}
