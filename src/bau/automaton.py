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

Its means (the owner's ask, 2026-11-10, after reading Conway-Research/automaton, MIT):
  earned budget  the owner may let it spend a share (`reinvest_pct`) of what it has really
                 earned, up to a cap (`reinvest_cap_usd`), on top of `budget_usd`. Earnings
                 that are not in the ledger do not count; nothing is borrowed.
  survival tier  like Conway's tiers, from its own numbers: normal (money left: hosted models
                 may help), low_compute (no money left: this computer's models only),
                 critical (7 days or fewer left to earn: said on the status page), dead.
  grow           once it has earned `grow_at_usd`, a card asks the owner to raise its posts a
                 day (what works, more of it). It never copies itself, never holds a wallet
                 and never edits its own code: the owner's rules (approvals are human).

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


CRITICAL_DAYS = 7


def free_only(home: Path | None = None) -> bool:
    """While it runs with no money left, nothing that costs money is used (no hosted models)."""
    return running(home) and status(home)["money_left_usd"] <= 0


def _human(by: str) -> None:
    if not by.startswith("human:"):
        raise PermissionError("only the owner starts or stops the automaton")


def start(home: Path, by: str, audience: str, per_day: int, budget_usd: float = 0.0,
          die_after_days: int = 30, now: dt.datetime | None = None,
          reinvest_pct: float = 0.0, reinvest_cap_usd: float = 0.0,
          grow_at_usd: float = 0.0) -> dict[str, Any]:
    _human(by)
    if budget_usd < 0 or not 1 <= int(die_after_days) <= 365:
        raise ValueError("budget is 0 or more dollars; days between 1 and 365")
    if not 0 <= reinvest_pct <= 100 or reinvest_cap_usd < 0 or grow_at_usd < 0:
        raise ValueError("reinvest is 0 to 100 percent; the cap and grow-at are 0 or more "
                         "dollars")
    from .fanvue import set_autopost
    set_autopost(home, True, by, audience, per_day)     # checks the audience and the number
    t = (now or _now()).isoformat(timespec="seconds")
    st = {"on": True, "dead": None, "started_at": t, "by": by, "budget_usd": float(budget_usd),
          "die_after_days": int(die_after_days), "audience": audience, "per_day": int(per_day),
          "reinvest_pct": float(reinvest_pct), "reinvest_cap_usd": float(reinvest_cap_usd),
          "grow_at_usd": float(grow_at_usd), "grown_at_usd": 0.0}
    _save(home, st)
    AuditLog(home / "audit" / "chain.jsonl").append(
        "automaton.start", by, {k: st[k] for k in ("budget_usd", "die_after_days", "audience",
                                                   "per_day", "reinvest_pct",
                                                   "reinvest_cap_usd", "grow_at_usd")})
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
    # Ledger.sale rows (gross_usd, fees, refund): what was kept counts; a refund lowers it and
    # never counts as income (2026-11-11: this read a `usd` field the ledger never writes).
    from .economics import received_usd
    kept = [(r, received_usd(r)) for r in _rows(eco / "revenue.jsonl", start_t)]
    income = [r for r, usd in kept if usd > 0]
    spent = round(sum(float(r.get("usd", 0)) for r in _rows(eco / "costs.jsonl", start_t)), 4)
    last = max([_ts(r["ts"]) for r in income], default=start_t)
    days = int(st.get("die_after_days", 30))
    left = days - (now - last).total_seconds() / 86400
    income_usd = round(max(sum(usd for _, usd in kept), 0.0), 2)
    earned = round(min(float(st.get("reinvest_cap_usd", 0)),
                       income_usd * float(st.get("reinvest_pct", 0)) / 100), 2)
    money_left = round(float(st.get("budget_usd", 0)) + earned - spent, 4)
    grow_at, grown = float(st.get("grow_at_usd", 0)), float(st.get("grown_at_usd", 0))
    tier = ("dead" if st.get("dead") else "critical" if left <= CRITICAL_DAYS else
            "normal" if money_left > 0 else "low_compute")
    return {"tier": tier, "money_left_usd": money_left, "earned_budget_usd": earned,
            "reinvest_pct": float(st.get("reinvest_pct", 0)),
            "reinvest_cap_usd": float(st.get("reinvest_cap_usd", 0)),
            "grow_ready": bool(grow_at > 0 and income_usd >= max(grow_at, grown * 2)
                               and st.get("on") and not st.get("dead")),
            "grow_at_usd": grow_at, "on": bool(st.get("on")), "dead": st.get("dead"),
            "started_at": st["started_at"],
            "day": int((now - start_t).total_seconds() // 86400) + 1,
            "income_usd": income_usd,
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
    if s["money_left_usd"] < 0:
        total = s["budget_usd"] + s["earned_budget_usd"]
        why = f"spent ${s['spent_usd']:.2f}, over its ${total:.2f} budget"
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


def grow(home: Path, by: str, per_day: int) -> dict[str, Any]:
    """The owner's Accept on the grow card: more posts a day, once it has earned grow_at."""
    _human(by)
    s = status(home)
    if not s.get("grow_ready"):
        raise ValueError("not earned enough to grow yet")
    if int(per_day) <= int(s.get("per_day") or 0):
        raise ValueError(f"growing means more than {s.get('per_day')} posts a day")
    from .fanvue import set_autopost
    set_autopost(home, True, by, str(s["audience"]), int(per_day))   # checks the maximum
    st = load(home)
    st.update(per_day=int(per_day), grown_at_usd=s["income_usd"])
    _save(home, st)
    AuditLog(home / "audit" / "chain.jsonl").append(
        "automaton.grow", by, {"per_day": int(per_day), "income_usd": s["income_usd"]})
    return status(home)
