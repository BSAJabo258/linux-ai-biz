"""The supervisor: keeps the team's boss honest (docs/TEAM.md).

The boss (a local model, e.g. Qwen) runs the job. When it gets stuck - going round in
circles (``LOOPING``), out of steps (``STEP_LIMIT``) or with no answer - the job goes to the
specialist on call (e.g. Claude) with a short note of what the boss tried. In ``auto`` mode
that happens by itself unless the owner's daily usage limit is reached; in ``ask`` mode the
job stops and says what it needs, so no paid model runs without the owner. A finished
answer is checked for facts (amounts, numbers, links, quoted words) that no tool result
backs; those are listed as unchecked, never silently passed as true. A double-check by the
specialist runs only when the owner allows paid calls (``auto``).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from .agents import RunResult

STUCK = {"LOOPING", "STEP_LIMIT"}
MODES = ("auto", "ask")

_FACTS = re.compile(
    r'https?://[^\s)\]>"\']+'                      # links
    r'|"[^"\n]{4,120}"'                             # quoted words
    r'|[$€£]\s?\d[\d,]*(?:\.\d+)?'                  # amounts
    r'|\b\d[\d,]*(?:\.\d+)?\s?%'                    # percentages
    r'|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d+\.\d+\b|\b\d{2,}\b')   # other numbers


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s).rstrip(".,;:").lower()


def facts(answer: str) -> list[str]:
    out = []
    for m in _FACTS.finditer(answer or ""):
        f = m.group(0).strip().rstrip(".,;:")
        f = f[1:-1] if f.startswith('"') and f.endswith('"') else f
        if f and f not in out:
            out.append(f)
    return out


def unchecked(answer: str, evidence: list[str]) -> list[str]:
    """The facts in an answer that appear in no tool result (or the task itself)."""
    pool = _norm(" ".join(evidence))
    return [f for f in facts(answer) if _norm(f) not in pool]


def stuck(res: RunResult) -> str | None:
    if res.status in STUCK:
        return res.status
    if res.status == "COMPLETED" and not (res.final_text or "").strip():
        return "NO_ANSWER"
    return None


def handover(task: str, res: RunResult, why: str) -> str:
    tried = [f"{c.get('capability')} ({'ok' if c.get('ok') else 'failed'})"
             for c in res.tool_calls][-12:]
    return (f"{task}\n\n---\nThe team's boss model stopped on this task: {why} after "
            f"{res.steps} steps. Tools it tried: {', '.join(tried) or 'none'}. "
            "Finish the task; say plainly what you could not do.")


def supervise(task: str, boss: Callable[[str], RunResult],
              specialist: Callable[[str], RunResult] | None, mode: str = "ask",
              over_limit: Callable[[], str | None] | None = None,
              verify: Callable[[str, list[str]], str] | None = None) -> RunResult:
    """Run the boss on the task; hand it to the specialist when the boss is stuck."""
    if mode not in MODES:
        raise ValueError(f"takeover must be one of {MODES}")
    res = boss(task)
    why = stuck(res)
    sup: dict[str, Any] = {"by": "boss", "boss_status": res.status}
    if why:
        sup["handed_over"] = why
        limit = over_limit() if over_limit else None
        if specialist is None:
            sup["next"] = ("the boss is stuck and no specialist is set: "
                           "`bau team set --specialist MODEL`")
        elif mode == "ask":
            sup["next"] = (f"the boss got stuck ({why}). To let the specialist take over "
                           "such jobs by itself: `bau team set --takeover auto`; or ask again "
                           "in other words")
        elif limit:
            sup["next"] = f"the specialist was not called: {limit}"
        else:
            first = res
            res = specialist(handover(task, first, why))
            res.cost_usd += first.cost_usd
            res.evidence = first.evidence + res.evidence
            sup.update(by="specialist", specialist_status=res.status)
        if sup["by"] == "boss":
            res.status = "NEEDS_OWNER"
    if res.status == "COMPLETED":
        sup["unchecked"] = unchecked(res.final_text, [task, *res.evidence])
        if verify is not None:
            sup["double_check"] = (verify(res.final_text, res.evidence) if mode == "auto"
                                   else "not double-checked: paid checks need "
                                        "`bau team set --takeover auto`")
    res.supervision = sup
    return res
