"""The open-source watch: Repo Scout on its own, weekly, across the nine technology
categories in data/scout_watch.yaml (`bau scout watch`, `bau scout shortlist`).

Each run sends a few searches per category and refreshes the seeds, under GitHub's rate
limits (stopping the moment GitHub says wait), tags what it finds with its categories and
keeps a dated snapshot of stars and last push, so rising projects stand out. The shortlist
tells apart what BAU already runs, what the Toolbox already researched and what is new,
and ranks by Scout's evidence-based score, the owner's category priority and the trend.
Nothing is installed or run, nothing is ever marked "adopt", and cost stays unknown until a
benchmark measures it.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

import yaml

from ..home import shipped_data
from .github import RateLimited, SourceError
from .plan import keywords

GROUPS = ("test_next", "watch", "already_have", "ignore")
COST = "unknown until benchmarked"
TEST_NEXT_AT = 40          # opportunity at or above this, and new: worth inspecting now


def load() -> dict[str, Any]:
    return yaml.safe_load((shipped_data() / "scout_watch.yaml").read_text())


def _snapshot(c: dict[str, Any], on: str) -> None:
    hist = [h for h in c.get("history", []) if h.get("on") != on]
    hist.append({"on": on, "stars": c["metadata"].get("stars"),
                 "pushed_at": c["metadata"].get("pushed_at")})
    c["history"] = sorted(hist, key=lambda h: h["on"])[-60:]


def watch(sc: Any, cat: dict[str, Any] | None = None, today: dt.date | None = None,
          searches: int | None = None, only: str | None = None) -> dict[str, Any]:
    cat = cat or load()
    on = (today or dt.date.today()).isoformat()
    n = searches or int(cat.get("searches", 2))
    out: dict[str, Any] = {"at": on, "categories": {}, "not_sent": [], "stopped": None}
    reached = False                    # at least one search or seed answered by GitHub
    for key, c in cat["categories"].items():
        if only and key != only:
            continue
        info: dict[str, Any] = {"searches": 0, "seeds": 0, "tagged": 0, "errors": []}
        tagged: set[str] = set()
        for q in c["queries"][:n]:
            if sc.stopped:
                out["not_sent"].append(f"{key}: search '{q}'")
                continue
            run = sc.find(q, max_queries=1, per_query=10, readmes=1)
            info["searches"] += 1
            sent = {s["q"] for s in run["searches"] if "found" in s}
            reached = reached or bool(sent)
            info["errors"] += [s["error"] for s in run["searches"] if "error" in s]
            tagged |= {cid for cid, cand in sc.candidates().items()
                       if sent & set(cand.get("queries", []))}
        for seed in c.get("seeds", []):
            if sc.stopped:
                out["not_sent"].append(f"{key}: seed {seed}")
                continue
            try:
                tagged.add(sc.add(seed, keywords(c["queries"][0]), f"watch:{key}")["id"])
                info["seeds"] += 1
                reached = True
            except RateLimited as e:
                sc.stopped = e
                out["not_sent"].append(f"{key}: seed {seed}")
            except (SourceError, ValueError, KeyError) as e:
                info["errors"].append(f"{seed}: {e}")
        store = sc.candidates()
        for cid in tagged & set(store):
            cand = store[cid]
            cand["categories"] = sorted(set(cand.get("categories", [])) | {key})
            _snapshot(cand, on)
        sc._save(store)
        info["tagged"] = len(tagged)
        out["categories"][key] = info
    if sc.stopped:
        out["stopped"] = f"GitHub asked to wait until {sc.stopped.when}"
    out["reached_github"] = reached
    sc.dir.mkdir(parents=True, exist_ok=True)
    with (sc.dir / "watch.jsonl").open("a") as fh:
        fh.write(json.dumps(out, sort_keys=True) + "\n")
    sc._record("scout.watch", {"at": on, "categories": sorted(out["categories"]),
                               "not_sent": len(out["not_sent"]), "stopped": out["stopped"]})
    return out


def trend(c: dict[str, Any], today: dt.date | None = None, days: int = 30) -> dict[str, Any]:
    end = today or dt.date.today()
    hist = [h for h in c.get("history", [])
            if (end - dt.date.fromisoformat(h["on"])).days <= days]
    if len(hist) < 2:
        return {"trend": "new to the watch", "gained": 0, "days": 0}
    first, last = hist[0], hist[-1]
    gained = (last.get("stars") or 0) - (first.get("stars") or 0)
    span = (dt.date.fromisoformat(last["on"]) - dt.date.fromisoformat(first["on"])).days
    word = ("rising" if gained >= max(25, 0.05 * (first.get("stars") or 0))
            else "falling" if gained < 0 else "steady")
    return {"trend": word, "gained": gained, "days": span}


def _toolbox_repos(home: Any) -> dict[str, str]:
    from ..toolbox import Toolbox
    return {e["repo"]: e["name"] for e in Toolbox(home).entries if e.get("repo")}


def shortlist(sc: Any, cat: dict[str, Any] | None = None,
              toolbox: dict[str, str] | None = None,
              today: dt.date | None = None) -> dict[str, list[dict[str, Any]]]:
    cat = cat or load()
    tb = {k.lower(): v for k, v in (_toolbox_repos(sc.home) if toolbox is None
                                    else toolbox).items()}
    running = {r.lower() for r in cat.get("integrated", [])}
    out: dict[str, list[dict[str, Any]]] = {g: [] for g in GROUPS}
    for c in sc.candidates().values():
        if not c.get("categories") or c.get("duplicate_of"):
            continue
        cid = c["id"]
        have = ("running in BAU" if cid in running else
                f"researched in the Toolbox ({tb[cid]})" if cid in tb else "new")
        tr = trend(c, today)
        prio = max(cat["categories"].get(k, {}).get("priority", 1) for k in c["categories"])
        opp = round(c["score"] * (0.7 + 0.15 * prio) + (10 if tr["trend"] == "rising" else 0),
                    1)
        why = list(c.get("blockers", [])) + list(c.get("needs", []))
        if tr["trend"] == "rising":
            why.insert(0, f"rising: +{tr['gained']} stars in {tr['days']} days")
        if c.get("unknowns"):
            why.append("not yet known: " + ", ".join(c["unknowns"]))
        if c["decision"] == "rejected":
            group, nxt = "ignore", "nothing to do"
        elif have != "new":
            group, nxt = "already_have", (
                "compare its latest release with what BAU runs" if have == "running in BAU"
                else "see `bau toolbox ask`; integrate when its turn comes")
        elif opp >= TEST_NEXT_AT:
            group, nxt = "test_next", (f"bau scout inspect {c['full_name']}, then a sandbox "
                                       "test and a benchmark; you decide")
        else:
            group, nxt = "watch", "check again next week"
        out[group].append({
            "repo": c["full_name"], "url": c.get("url"), "categories": c["categories"],
            "claims": c["claimed"]["description"], "have": have, "trend": tr["trend"],
            "gained": tr["gained"], "score": c["score"], "coverage": c["evidence_coverage"],
            "opportunity": opp, "licence": c["license"].get("status"),
            "security": c["security"]["status"], "why": why, "next": nxt, "cost": COST})
    for g in out.values():
        g.sort(key=lambda i: -i["opportunity"])
    return out


def report(sl: dict[str, list[dict[str, Any]]], top: int = 5) -> str:
    titles = {"test_next": "Test next", "watch": "Watch",
              "already_have": "Already have", "ignore": "Ignored"}
    lines = ["Open-source watch: what is worth your time this week.", ""]
    for g in GROUPS:
        items = sl.get(g, [])
        lines.append(f"{titles[g]} ({len(items)})")
        for i in items[:top if g != "ignore" else 3]:
            reason = "; ".join(i["why"][:2]) or "no notes"
            lines.append(f"  - {i['repo']} [{', '.join(i['categories'])}] "
                         f"opportunity {i['opportunity']}, {i['have']}: {reason}")
        lines.append("")
    lines.append("Descriptions are the projects' own claims. Nothing is installed or run: "
                 "every step needs your go-ahead. Cost is unknown until a benchmark measures it.")
    return "\n".join(lines)
