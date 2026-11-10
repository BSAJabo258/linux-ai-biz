"""The automaton: make money or die (the owner's choice, 2026-11-10).

Switched on by the owner (`bau automaton start`), Jarvis runs the money loop by himself:
the autopilot draws the creator's pictures on this computer (with their age check), the local
model writes the captions, they are queued WITHOUT waiting for the owner's Accept, autopost
puts them on Fanvue, and the earnings come back into the ledger. The owner sees a daily
report and can stop it at any time (`bau automaton stop`, or HOLD).

Two lines it cannot cross:
  money  it may spend at most `budget_usd` from its start (the owner chose $0: only this
         computer's own models and free tools; hosted models are skipped while it runs)
  time   it must earn something every `die_after_days` (30). It does not, or it spends past
         its budget: it dies. Dying puts BAU on governor HOLD (only read-only actions run),
         stops autopost, and says why on the status page. Only the owner revives it.

What stays the same while it runs, because it is law or the platforms' terms, not a
preference: every content check (21+, the AI label, nothing about minors, the owner's
explicit limits), and no cold email or texts to people who never signed up.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from .audit import AuditLog
from .home import atomic_write_json, bau_home

ACTOR = "automaton"


def _path(home: Path) -> Path:
    return home / "automaton" / "state.json"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _ts(s: str) -> dt.datetime:
    t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=dt.UTC)


def load(home: Path | None = None) -> dict[str, Any]:
    try:
        return json.loads(_path(home or bau_home()).read_text())
    except (OSError, ValueError):
        return {}


def _save(home: Path, st: dict[str, Any]) -> None:
    _path(home).parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(_path(home), st)


def running(home: Path | None = None) -> bool:
    st = load(home)
    return bool(st.get("on")) and not st.get("dead")


def free_only(home: Path | None = None) -> bool:
    """While it runs on a $0 budget, nothing that costs money is used (no hosted models)."""
    st = load(home)
    return running(home) and float(st.get("budget_usd", 0)) <= 0


def _human(by: str) -> None:
    if not by.startswith("human:"):
        raise PermissionError("only the owner starts or stops the automaton")


def start(home: Path, by: str, audience: str, per_day: int, budget_usd: float = 0.0,
          die_after_days: int = 30, now: dt.datetime | None = None) -> dict[str, Any]:
    _human(by)
    if budget_usd < 0 or not 1 <= int(die_after_days) <= 365:
        raise ValueError("budget is 0 or more dollars; days between 1 and 365")
    from .fanvue import set_autopost
    set_autopost(home, True, by, audience, per_day)     # checks the audience and the number
    t = (now or _now()).isoformat(timespec="seconds")
    st = {"on": True, "dead": None, "started_at": t, "by": by, "budget_usd": float(budget_usd),
          "die_after_days": int(die_after_days), "audience": audience, "per_day": int(per_day)}
    _save(home, st)
    AuditLog(home / "audit" / "chain.jsonl").append(
        "automaton.start", by, {k: st[k] for k in ("budget_usd", "die_after_days", "audience",
                                                   "per_day")})
    return status(home, now)


def stop(home: Path, by: str) -> dict[str, Any]:
    _human(by)
    st = load(home)
    st["on"] = False
    _save(home, st)
    from .fanvue import set_autopost
    set_autopost(home, False, by)
    AuditLog(home / "audit" / "chain.jsonl").append("automaton.stop", by, {})
    return status(home)


def _rows(path: Path, since: dt.datetime) -> list[dict[str, Any]]:
    out = []
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            r = json.loads(line)
            if _ts(r["ts"]) >= since:
                out.append(r)
        except (ValueError, KeyError, TypeError):
            continue
    return out


def status(home: Path | None = None, now: dt.datetime | None = None) -> dict[str, Any]:
    home = home or bau_home()
    st = load(home)
    if not st.get("started_at"):
        return {"on": False}
    now = now or _now()
    start_t = _ts(st["started_at"])
    eco = home / "economics"
    income = [r for r in _rows(eco / "revenue.jsonl", start_t) if float(r.get("usd", 0)) > 0]
    spent = round(sum(float(r.get("usd", 0)) for r in _rows(eco / "costs.jsonl", start_t)), 4)
    last = max([_ts(r["ts"]) for r in income], default=start_t)
    days = int(st.get("die_after_days", 30))
    left = days - (now - last).total_seconds() / 86400
    return {"on": bool(st.get("on")), "dead": st.get("dead"), "started_at": st["started_at"],
            "day": int((now - start_t).total_seconds() // 86400) + 1,
            "income_usd": round(sum(float(r["usd"]) for r in income), 2),
            "spent_usd": spent, "budget_usd": float(st.get("budget_usd", 0)),
            "last_income_at": last.isoformat(timespec="seconds") if income else None,
            "days_left_to_earn": round(max(left, 0.0), 1), "die_after_days": days,
            "audience": st.get("audience"), "per_day": st.get("per_day")}


def check(home: Path | None = None, now: dt.datetime | None = None) -> dict[str, Any]:
    """Run by the autopilot each tick: alive, or dead and why."""
    home = home or bau_home()
    if not running(home):
        return status(home, now)
    s = status(home, now)
    why = None
    if s["spent_usd"] > s["budget_usd"]:
        why = f"spent ${s['spent_usd']:.2f}, over its ${s['budget_usd']:.2f} budget"
    elif s["days_left_to_earn"] <= 0:
        why = f"no income in {s['die_after_days']} days"
    if why is None:
        return s
    st = load(home)
    st["dead"] = {"why": why, "at": (now or _now()).isoformat(timespec="seconds")}
    _save(home, st)
    from .governor import Governor
    Governor(home).hold(f"the automaton died: {why}. `bau automaton start` to try again",
                        by=ACTOR)
    try:                                   # autopost off too, so nothing posts after death
        from .fanvue import autopost_choice
        choice = autopost_choice(home) or {}
        if choice.get("on"):
            atomic_write_json(home / "fanvue" / "autopost.json",
                              {**choice, "on": False, "stopped_by": ACTOR, "why": why})
    except OSError:
        pass
    AuditLog(home / "audit" / "chain.jsonl").append("automaton.died", ACTOR, {"why": why})
    return status(home, now)
