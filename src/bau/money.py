"""Is the money machine running? (the owner, 2026-11-18: "test all values to make sure this is
money making ready ... I don't see no activities").

Every link from the creator to Fanvue earnings, in the order the money flows, each read live
from its real record on this computer, with the exact fix when it is not ready. Nothing here
changes anything: ``bau money`` only looks. The operations world shows the same score.

The links that must all be ready before Jarvis can earn by himself:
  creator profile -> boss model -> pictures running -> Fanvue app keys -> Fanvue connected ->
  prices -> autopilot on -> autopost on -> no HOLD
Then what has really happened: posts waiting for you, queued, posted, money received.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

Probe = Callable[[str], Any]


def _probe(what: str) -> Any:
    """Live facts about this computer, read-only."""
    from . import setup_steps
    if what == "pictures_running":
        return setup_steps._answers("http://127.0.0.1:8188/system_stats")
    if what == "pictures_installed":
        return setup_steps.pictures_installed()
    if what == "autopilot_timer":
        return bool(setup_steps._probe("autopilot"))
    if what == "fanvue_keys":
        from . import fanvue
        try:
            fanvue.app_credentials()
        except fanvue.FanvueError:
            return False
        return True
    raise ValueError(what)


def _boss(home: Path) -> tuple[bool, str]:
    from . import team
    from .registry import CapabilityRegistry
    boss = team.show(home).get("boss")
    if not boss:
        return False, "no boss model named"
    p = home / "registry" / "capabilities.yaml"
    rec = CapabilityRegistry(p).data.get("model", {}).get(boss, {}) if p.exists() else {}
    if rec.get("status") not in ("APPROVED", "ACTIVE"):
        return False, f"{boss} is not approved (status {rec.get('status') or 'unknown'})"
    return True, boss


def links(home: Path, probe: Probe | None = None) -> list[dict[str, Any]]:
    """Each link: name, ok, what it found, and the fix (the exact command or card)."""
    import yaml

    from . import autopilot, fanvue, setup_steps
    from .governor import hold_reason
    probe = probe or _probe
    out: list[dict[str, Any]] = []

    def add(name: str, ok: bool, found: str, fix: str) -> None:
        out.append({"link": name, "ok": bool(ok), "found": found, "fix": "" if ok else fix})

    prof_path = setup_steps._profile(home)
    prof = (yaml.safe_load(prof_path.read_text()) or {}) if prof_path else {}
    add("creator profile", prof_path is not None,
        prof_path.name if prof_path else "none",
        "bau creator init, then fill in her details (docs/VIRTUAL-CREATOR.md)")
    ok, found = _boss(home)
    add("boss model (writes captions, runs the agents)", ok, found,
        "approve a local model after its benchmark, then: bau team set --boss MODEL (docs/TEAM.md)")
    running = bool(probe("pictures_running"))
    add("pictures (ComfyUI on this computer)", running,
        "running" if running else ("installed, not running" if probe("pictures_installed")
                                   else "not set up"),
        "sudo systemctl start bau-pictures.service" if probe("pictures_installed")
        else "press Accept on the 'Set up pictures on this computer' card in Jarvis")
    keys = bool(probe("fanvue_keys"))
    add("Fanvue app keys", keys, "on this computer" if keys else "missing",
        "press Accept on the 'Make your Fanvue app' card in Jarvis (docs/FANVUE.md)")
    connected = fanvue.TokenStore(home).load() is not None
    add("Fanvue connected", connected, "connected" if connected else "not connected",
        "bau fanvue login")
    prices = prof.get("prices") or {}
    add("prices", bool(prices), ", ".join(f"{k} ${v}" for k, v in prices.items()) or "not set",
        "press Accept on the 'Set your Fanvue prices' card in Jarvis")
    timer = bool(probe("autopilot_timer"))
    paused = bool(autopilot.status(home).get("paused"))
    add("autopilot (works every 30 minutes)", timer and not paused,
        "paused by you" if timer and paused else ("on" if timer else "off"),
        "bau autopilot resume" if timer else
        "press Accept on the 'Let Jarvis work on his own' card in Jarvis")
    choice = fanvue.autopost_choice(home) or {}
    add("autopost (Fanvue posts by themselves)", bool(choice.get("on")),
        (f"on, {choice.get('per_day')} a day to {choice.get('audience')}" if choice.get("on")
         else "off"),
        "bau fanvue autopost on --audience subscribers --per-day 1 (or the card in Jarvis)")
    held = hold_reason(home)
    add("no HOLD", held is None, held or "none", "bau governor release (after you check why)")
    return out


def activity(home: Path) -> dict[str, Any]:
    """What has really happened: the queue and the money received, from the records."""
    import datetime as dt

    from . import fanvue
    from .automaton import _rows
    from .economics import received_usd
    q = fanvue.Queue(home)
    items = q.items()
    rows = _rows(home / "economics" / "revenue.jsonl", dt.datetime(1970, 1, 1, tzinfo=dt.UTC))
    return {"waiting_for_you": len(q.review()), "queued": len(q.pending()),
            "posted": sum(i["status"] == "POSTED" for i in items),
            "money_received_usd": round(sum(received_usd(r) for r in rows), 2)}


def summary(home: Path, probe: Probe | None = None) -> dict[str, Any]:
    ls = links(home, probe)
    missing = [link for link in ls if not link["ok"]]
    return {"ready": len(ls) - len(missing), "of": len(ls),
            "next": missing[0]["link"] if missing else None,
            "next_fix": missing[0]["fix"] if missing else None}


def report(home: Path, probe: Probe | None = None) -> str:
    ls = links(home, probe)
    lines = ["The money machine, link by link (read live, nothing changed):", ""]
    for link in ls:
        mark = "✓" if link["ok"] else "✗"
        lines.append(f"{mark} {link['link']}: {link['found']}")
        if not link["ok"]:
            lines.append(f"    fix: {link['fix']}")
    a = activity(home)
    ready = sum(link["ok"] for link in ls)
    lines += ["", f"{ready} of {len(ls)} links ready.",
              f"What happened: {a['waiting_for_you']} picture(s) waiting for your Accept, "
              f"{a['queued']} queued, {a['posted']} posted, ${a['money_received_usd']:.2f} "
              "received."]
    if ready == len(ls):
        lines.append("Everything is ready: Jarvis draws, captions and posts by himself.")
    else:
        first = next(link for link in ls if not link["ok"])
        lines.append(f"Start here: {first['fix']}")
    return "\n".join(lines)
