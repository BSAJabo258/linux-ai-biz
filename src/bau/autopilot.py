"""Autopilot: Jarvis works on his own, all the time, and grows (docs/AUTOPILOT.md).

The owner's ask (2026-11-02): autonomous work that actually runs and keeps going, a vote that
knows good from bad, questions only when they matter, and the owner able to talk to it any
time. Three lanes:

  GO    research, scanning, inspecting, sandbox tests, drafts: just done, logged.
  VOTE  adding or enabling an ability: two of three voters - the rules (they can veto alone),
        the evidence (security scan clean and licence fine), the judge (the compass) - then
        done and reported.
  ASK   money, posting, legal, deleting, keys, approvals, and any kind not listed here: one
        question for the owner; that task waits, everything else keeps going.

The compass (data/autopilot_compass.yaml, the owner's copy in BAU_HOME/autopilot/) points
every scan, vote and job at the business. Approvals stay human-only: the autopilot has no
tool that approves, and an ASK task runs only after a human answered yes.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from .audit import AuditLog
from .home import shipped_data
from .virtual_creator import MINOR_REFERENCE

GO = {"scan", "inspect", "sandbox_test", "research", "draft", "learn"}
VOTE = {"add_tool", "enable_ability", "run_job"}
# Everything else asks; listed so the docs and the tests can name them.
ASK = {"post", "spend", "legal", "delete", "keys", "approve"}
OK_LICENCES = re.compile(r"^(MIT|Apache-2\.0|BSD|ISC|MPL|0BSD|Unlicense|Zlib|CC0)", re.I)
MAX_STEPS = 20
Handler = Callable[[dict[str, Any]], dict[str, Any]]


def lane(kind: str) -> str:
    return "GO" if kind in GO else "VOTE" if kind in VOTE else "ASK"


# ------------------------------------------------------------------ the compass
def compass(home: Path) -> dict[str, Any]:
    own = home / "autopilot" / "compass.yaml"
    src = own if own.exists() else shipped_data() / "autopilot_compass.yaml"
    return yaml.safe_load(src.read_text()) or {}


def _avoided(text: str, c: dict[str, Any]) -> str | None:
    low = text.lower()
    return next((w for w in c.get("avoid", []) if w.lower() in low), None)


def score(text: str, c: dict[str, Any], focus: str = "") -> float:
    """How well a task points at the business; at or below 0 means not at all."""
    if _avoided(text, c):
        return -1.0
    low = text.lower()
    s = float(sum(g.get("weight", 1) for g in c.get("goals", [])
                  for w in g.get("words", []) if w.lower() in low))
    return s + (10.0 if focus and focus.lower() in low else 0.0)


# ------------------------------------------------------------------ state
def _path(home: Path) -> Path:
    return home / "autopilot" / "state.json"


def _load(home: Path) -> dict[str, Any]:
    try:
        return json.loads(_path(home).read_text())
    except (OSError, ValueError):
        return {"paused": False, "focus": "", "tasks": []}


def _save(home: Path, st: dict[str, Any]) -> None:
    p = _path(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1))
    tmp.replace(p)


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def _audit(home: Path, event: str, who: str, data: dict[str, Any]) -> None:
    AuditLog(home / "audit" / "chain.jsonl").append(f"autopilot.{event}", who, data)


def add(home: Path, kind: str, title: str, detail: dict[str, Any] | None = None,
        source: str = "autopilot") -> dict[str, Any] | None:
    """Queue a task; the same open kind and title is never queued twice."""
    st = _load(home)
    if any(t["kind"] == kind and t["title"] == title and t["state"] in
           ("queued", "running", "waiting_owner") for t in st["tasks"]):
        return None
    t = {"id": "ap_" + secrets.token_hex(4), "kind": kind, "title": title[:200],
         "detail": detail or {}, "lane": lane(kind), "state": "queued", "source": source,
         "created": _now(), "note": ""}
    st["tasks"].append(t)
    _save(home, st)
    _audit(home, "queued", source, {"task": t["id"], "kind": kind, "title": t["title"],
                                     "lane": t["lane"]})
    return t


def next_task(st: dict[str, Any], c: dict[str, Any] | None = None) -> dict[str, Any] | None:
    c = c or {}
    queued = [t for t in st["tasks"] if t["state"] == "queued"]
    if not queued:
        return None
    if not c:
        c = yaml.safe_load((shipped_data() / "autopilot_compass.yaml").read_text())
    return max(queued, key=lambda t: score(t["title"], c, st.get("focus", "")))


# ------------------------------------------------------------------ the vote
def vote(task: dict[str, Any], c: dict[str, Any]) -> dict[str, Any]:
    d, text = task.get("detail", {}), task["title"]
    veto = None
    if MINOR_REFERENCE.search(text):
        veto = "refers to minors"
    elif (w := _avoided(text, c)):
        veto = f"on the never list ({w})"
    elif d.get("licence") and not OK_LICENCES.match(str(d["licence"])):
        veto = f"licence {d['licence']} does not allow business use"
    elif task["kind"] == "add_tool" and d.get("tested") is not True:
        veto = "not tested in the sandbox"
    votes = {"rules": veto is None,
             "evidence": d.get("security") == "clean" and bool(d.get("licence")),
             "judge": score(text, c) > 0}
    yes = sum(votes.values())
    return {"votes": votes, "yes": yes, "veto": veto, "passed": veto is None and yes >= 2}


# ------------------------------------------------------------------ the worker
def _finish(home: Path, st: dict[str, Any], t: dict[str, Any], out: dict[str, Any]) -> None:
    ok = bool(out.get("ok"))
    t["state"] = "done" if ok else "failed"
    t["note"] = str(out.get("evidence") or out.get("error") or "")[:300]
    t["finished"] = _now()
    _audit(home, "done" if ok else "failed", "autopilot",
           {"task": t["id"], "title": t["title"], "note": t["note"]})
    _save(home, st)
    for kind, title, detail in out.get("follow_ups") or []:
        add(home, kind, title, detail, source=f"follow-up of {t['id']}")


def step(home: Path, handlers: dict[str, Handler]) -> dict[str, Any] | None:
    st = _load(home)
    if st.get("paused"):
        return {"paused": True}
    c = compass(home)
    t = next_task(st, c)
    if t is None:
        return None
    if t["lane"] == "ASK" and t["detail"].get("answer") != "yes":
        t["state"] = "waiting_owner"
        t["question"] = t["detail"].get("question") or f"May I do this: {t['title']}?"
        _save(home, st)
        _audit(home, "asked", "autopilot", {"task": t["id"], "question": t["question"]})
        return {"task": t["id"], "state": t["state"]}
    if t["lane"] == "VOTE":
        v = vote(t, c)
        t["vote"] = v
        if not v["passed"]:
            t["state"], t["note"] = "vetoed", v["veto"] or f"voted down ({v['yes']} of 3)"
            _save(home, st)
            _audit(home, "vetoed" if v["veto"] else "voted_down", "autopilot",
                   {"task": t["id"], "title": t["title"], "vote": v})
            return {"task": t["id"], "state": t["state"]}
    fn = handlers.get(t["kind"])
    if fn is None:
        t["state"], t["note"] = "blocked", f"no handler for {t['kind']} yet; nothing was done"
        _save(home, st)
        _audit(home, "blocked", "autopilot", {"task": t["id"], "note": t["note"]})
        return {"task": t["id"], "state": t["state"]}
    t["state"], t["started"] = "running", _now()
    _save(home, st)
    try:
        out = fn(t) or {}
    except Exception as e:  # one broken job must not stop the rest
        out = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    _finish(home, st, t, out)
    return {"task": t["id"], "state": t["state"]}


def run(home: Path, handlers: dict[str, Handler], max_steps: int = MAX_STEPS
        ) -> dict[str, Any]:
    done = []
    for _ in range(max_steps):
        r = step(home, handlers)
        if r is None:
            break
        if r.get("paused"):
            return {"paused": True, "steps": done}
        done.append(r)
    return {"paused": False, "steps": done}


# ------------------------------------------------------------------ the owner
def _human(by: str) -> None:
    if not by.startswith("human:"):
        raise PermissionError("only the owner can do that")


def _set(home: Path, by: str, **kv: Any) -> None:
    _human(by)
    st = _load(home)
    st.update(kv)
    _save(home, st)
    _audit(home, "owner", by, kv)


def pause(home: Path, by: str) -> None:
    _set(home, by, paused=True)


def resume(home: Path, by: str) -> None:
    _set(home, by, paused=False)


def focus(home: Path, what: str, by: str) -> None:
    _set(home, by, focus=" ".join(what.split())[:80])


def skip(home: Path, task_id: str, by: str) -> None:
    _human(by)
    st = _load(home)
    for t in st["tasks"]:
        if t["id"] == task_id and t["state"] in ("queued", "waiting_owner"):
            t["state"], t["note"] = "skipped", "the owner skipped it"
    _save(home, st)
    _audit(home, "skipped", by, {"task": task_id})


def questions(home: Path) -> list[dict[str, Any]]:
    return [{"id": t["id"], "question": t.get("question", ""), "title": t["title"],
             "options": ["yes", "no"]}
            for t in _load(home)["tasks"] if t["state"] == "waiting_owner"]


def answer(home: Path, task_id: str, choice: str, by: str) -> dict[str, Any]:
    _human(by)
    if choice not in ("yes", "no"):
        raise ValueError("answer yes or no")
    st = _load(home)
    t = next((t for t in st["tasks"] if t["id"] == task_id and t["state"] == "waiting_owner"),
             None)
    if t is None:
        return {"error": "nothing waiting with that id"}
    t["detail"]["answer"] = choice
    t["state"] = "queued" if choice == "yes" else "declined"
    _save(home, st)
    _audit(home, "answered", by, {"task": task_id, "answer": choice})
    return {"task": task_id, "state": t["state"]}


# ------------------------------------------------------------------ reports
STATES = ("queued", "running", "waiting_owner", "done", "failed", "vetoed", "blocked",
          "declined", "skipped")


def status(home: Path) -> dict[str, Any]:
    st = _load(home)
    out: dict[str, Any] = {s: 0 for s in STATES}
    for t in st["tasks"]:
        out[t["state"]] = out.get(t["state"], 0) + 1
    out.update(paused=st.get("paused", False), focus=st.get("focus", ""),
               questions=len(questions(home)))
    return out


def digest(home: Path, hours: int = 24) -> str:
    since = (dt.datetime.now(dt.UTC) - dt.timedelta(hours=hours)).isoformat()
    st = _load(home)
    done = [t for t in st["tasks"] if t["state"] == "done" and t.get("finished", "") >= since]
    lines = [f"Autopilot, last {hours} hours: {len(done)} done."]
    lines += [f"- {t['title']}" + (f": {t['note']}" if t["note"] else "") for t in done[:10]]
    for state, said in (("vetoed", "stopped by the vote"), ("failed", "failed"),
                        ("blocked", "waiting for a handler")):
        n = sum(1 for t in st["tasks"] if t["state"] == state)
        if n:
            lines.append(f"{n} {said}.")
    q = len(questions(home))
    if q:
        lines.append(f"{q} question{'s' * (q != 1)} for you.")
    if st.get("paused"):
        lines.append("Paused by you.")
    return "\n".join(lines)
