"""The toolbox: open-source tools other people already built for the problems Jarvis meets
(connecting models to tools, stopping made-up answers, memory, agents, local models, voice,
video). Jarvis looks here before guessing how to do something.

Every entry in ``data/toolbox.yaml`` was researched on the date at the top of the file and
names the pages it came from. What a project says about itself is a claim; only Repo Scout's
inspection (``bau toolbox check NAME``: its GitHub record, then a quarantined download and a
static scan) turns it into something BAU has looked at. Nothing here installs or runs a tool.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Any

import yaml

from .home import bau_home, shipped_data

CATEGORIES = ("connect", "claude-code", "docs-grounding", "gateway", "grounding",
              "structured-output", "guardrails", "evals", "context-engineering", "agents",
              "memory", "local-models", "automation", "speech-to-text", "text-to-speech",
              "wake-word", "voice-assistant", "video-editing", "generation", "browser",
              "computer-use", "documents")
FIELDS = ("name", "repo", "url", "category", "problem", "how_used", "licence", "stars",
          "last_activity", "sources", "caveats")
REPO = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STATUSES = ("have", "partial", "gap")
# How a researched tool would join BAU: used as it is, wrapped behind a BAU adapter (so
# BAU's permissions, audit and approvals stay in charge), later (worth it, not yet), or
# skipped because BAU already does the job.
PLANS = ("direct", "adapter", "later", "skip")
LAYER_FIELDS = ("id", "name", "what", "status", "in_bau", "tools", "risk", "rules")
CLAIMS = re.compile(r"\b(compliant|compliance-ready|guarantee[ds]?|risk-free)\b", re.I)
STOP = set("a an and are as at be but by can do does for from get go how i in is it its "
           "me model models my of on or so that the them then this to up use what when "
           "with you your ai jarvis him he she they keeps keep want need help thing things "
           "back stop make".split())
# Plain words the owner uses -> the words tools use for the same problem.
SAY = {"making things up": "hallucination grounded faithfulness",
       "make things up": "hallucination grounded faithfulness",
       "made up": "hallucination grounded faithfulness",
       "delusion": "hallucination grounded faithfulness", "lie": "hallucination grounded",
       "wrong answer": "hallucination evaluation", "forget": "memory remember recall",
       "remember": "memory recall", "connect": "connect mcp connector",
       "connector": "connect mcp", "plug in": "connect mcp", "talk": "speech voice",
       "listen": "speech-to-text transcribe", "hear": "speech-to-text transcribe",
       "speak": "text-to-speech voice", "voice": "speech voice",
       "edit video": "video-editing ffmpeg", "clip": "video short",
       "offline": "local-models local", "free model": "local-models local",
       "test": "evals evaluation", "check answer": "evals evaluation",
       "structured": "structured-output schema", "json": "structured-output schema",
       "agent": "agents agent", "workflow": "automation workflow",
       "up to date docs": "docs-grounding documentation"}


def _stem(w: str) -> str:
    for suf in ("ness", "ing", "ed", "es", "ly", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            w = w[:-len(suf)]
            if len(w) > 3 and w[-1] == w[-2]:
                w = w[:-1]                       # forgetting -> forgett -> forget
            break
    return w


def _terms(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP]


class Toolbox:
    def __init__(self, home: Path | None = None, data: Path | None = None):
        self.home = home or bau_home()
        raw = yaml.safe_load((data or shipped_data() / "toolbox.yaml").read_text()) or {}
        self.checked = str(raw.get("checked", ""))
        self.entries: list[dict[str, Any]] = list(raw.get("entries") or [])

    # ---------------------------------------------------------------- the catalogue itself
    def problems(self) -> list[str]:
        out, seen = [], set()
        for i, e in enumerate(self.entries):
            who = e.get("name") or f"entry {i}"
            missing = [f for f in FIELDS if f not in e]
            if missing:
                out.append(f"{who}: missing {', '.join(missing)}")
                continue
            if not REPO.match(str(e["repo"])) or {".", ".."} & set(str(e["repo"]).split("/")):
                out.append(f"{who}: repo must be OWNER/NAME")
            elif e["repo"].lower() in seen:
                out.append(f"{who}: {e['repo']} is listed twice")
            seen.add(str(e["repo"]).lower())
            if e["category"] not in CATEGORIES:
                out.append(f"{who}: unknown category {e['category']!r}")
            urls = [e["url"], *(e["sources"] or [])]
            if not e["sources"] or not all(str(u).startswith("https://") for u in urls):
                out.append(f"{who}: needs https sources it was checked against")
            if any(CLAIMS.search(str(e[f])) for f in ("problem", "how_used", "caveats")):
                out.append(f"{who}: no compliance or guarantee claims")
            if "checked" in e and not DATE.match(str(e["checked"])):
                out.append(f"{who}: checked must be a date like 2026-10-11")
        return out

    def find(self, name: str) -> dict[str, Any] | None:
        n = name.strip().lower()
        return next((e for e in self.entries
                     if n in (e["name"].lower(), e["repo"].lower())), None)

    # ---------------------------------------------------------------- asking
    def ask(self, question: str, category: str | None = None,
            k: int = 5) -> list[dict[str, Any]]:
        """The tools that fit a plain-words question, best first, each with what BAU
        actually knows about it."""
        q = question.lower()
        words = _terms(q + " " + " ".join(v for s, v in SAY.items() if s in q))
        rows = [e for e in self.entries if category in (None, e["category"])]
        scored = []
        for e in rows:
            fields = ((e["category"].replace("-", " "), 3), (e["name"], 5),
                      (e["problem"], 2), (e["how_used"], 1))
            have = [(set(_terms(text)), w) for text, w in fields]
            score = sum(w for t in set(words) for terms, w in have if t in terms)
            if score or not words:
                scored.append((score, e))
        scored.sort(key=lambda s: -s[0])
        cands = self._scout()
        return [self._public(e, cands) for _, e in scored[:k]]

    def _scout(self) -> dict[str, Any]:
        try:
            return json.loads((self.home / "scout" / "candidates.json").read_text())
        except (OSError, ValueError):
            return {}

    def _public(self, e: dict[str, Any], cands: dict[str, Any]) -> dict[str, Any]:
        out = {f: e[f] for f in FIELDS}
        c = cands.get(e["repo"].lower()) or {}
        if c.get("inspected"):
            ins = c["inspected"]
            out["evidence"] = f"inspected {str(ins.get('at', ''))[:10]}: {ins.get('verdict')}"
            out["scout_decision"] = c.get("decision")
            out["next"] = f"bau scout report   (Scout's decision: {c.get('decision')})"
        else:
            out["evidence"] = (f"claimed: research checked {e.get('checked', self.checked)}, "
                               "not inspected yet")
            out["next"] = (f"bau toolbox check {shlex.quote(e['name'])}"
                           if e["url"].startswith("https://github.com/") else
                           "not on GitHub: read its page; models need `bau models bench`")
        return out

    # ---------------------------------------------------------------- going to get it
    def check(self, name: str, source: Any = None, cloner: Any = None, audit: Any = None,
              actor: str = "human:owner") -> dict[str, Any]:
        """Hand one toolbox entry to Repo Scout: its GitHub record, then a quarantined,
        never-run download and a static scan. Licence and security gates still decide."""
        from .scout import Scout
        e = self.find(name)
        if e is None:
            raise KeyError(f"{name} is not in the toolbox: `bau toolbox ask` lists what is")
        if not e["url"].startswith("https://github.com/"):
            raise ValueError(f"{e['name']} is not on GitHub ({e['url']}); models are "
                             "checked with `bau models bench` instead")
        sc = Scout(self.home, source, audit, actor, cloner)
        sc.add(e["repo"], keywords=_terms(e["problem"])[:8], origin="toolbox")
        return sc.inspect(e["repo"])


class CapabilityMap:
    """Jarvis's abilities as layers (``data/capability_map.yaml``): what BAU already has
    for each, which toolbox tools could fill the gaps and how, and the build order."""

    def __init__(self, data: Path | None = None, toolbox: Toolbox | None = None):
        raw = yaml.safe_load((data or shipped_data() / "capability_map.yaml").read_text())
        self.checked = str((raw or {}).get("checked", ""))
        self.layers: list[dict[str, Any]] = list((raw or {}).get("layers") or [])
        self.toolbox = toolbox or Toolbox()

    def problems(self) -> list[str]:
        out, ids = [], set()
        for i, layer in enumerate(self.layers):
            who = layer.get("id") or f"layer {i}"
            missing = [f for f in LAYER_FIELDS if f not in layer]
            if missing:
                out.append(f"{who}: missing {', '.join(missing)}")
                continue
            if who in ids:
                out.append(f"{who}: listed twice")
            ids.add(who)
            if layer["status"] not in STATUSES:
                out.append(f"{who}: status must be one of {', '.join(STATUSES)}")
            if layer["status"] != "have" and not layer.get("next"):
                out.append(f"{who}: say what comes next")
            for have in layer["in_bau"]:
                extra = set(have) - {"path", "does"}
                if extra or not have.get("does"):
                    out.append(f"{who}: in_bau entries are {{path, does}}; quote a value "
                               f"that contains a comma (extra keys: {sorted(extra)})")
            for t in layer["tools"]:
                if self.toolbox.find(str(t.get("name", ""))) is None:
                    out.append(f"{who}: {t.get('name')!r} is not in the toolbox")
                if t.get("plan") not in PLANS:
                    out.append(f"{who}: {t.get('name')}: plan must be one of {', '.join(PLANS)}")
                if not t.get("why"):
                    out.append(f"{who}: {t.get('name')}: say why")
            text = " ".join(str(layer.get(f, "")) for f in ("what", "next", "rules"))
            if CLAIMS.search(text) or any(CLAIMS.search(str(t.get("why", "")))
                                          for t in layer["tools"]):
                out.append(f"{who}: no compliance or guarantee claims")
        return out

    def layer(self, lid: str) -> dict[str, Any]:
        hit = next((x for x in self.layers if x["id"] == lid), None)
        if hit is None:
            raise KeyError(f"no layer {lid!r}; have {', '.join(x['id'] for x in self.layers)}")
        return hit

    def match(self, task: str) -> dict[str, Any] | None:
        """The layer that best fits a plain-words task, or None when nothing does.

        Matching uses the same stemming and plain-word aliases as the toolbox, so
        "connect to Gmail" reaches the connectors layer and "fill in a form"
        reaches web interaction. It is a hint for the owner, never a permission.
        """
        if not task.strip():
            return None
        words = set(_terms(task + " " + " ".join(v for s, v in SAY.items()
                                                  if s in task.lower())))
        best, best_hits = None, 0
        for layer in self.layers:
            hay = " ".join([layer["id"], layer["name"], layer["what"], layer.get("next", ""),
                            *layer.get("rules", []),
                            *[t.get("name", "") for t in layer.get("tools", [])]])
            hits = len(words & set(_terms(hay)))
            if hits > best_hits:
                best, best_hits = layer, hits
        return best

    def show(self, lid: str) -> dict[str, Any]:
        """One layer, each tool with what BAU actually knows about it."""
        layer = self.layer(lid)
        cands = self.toolbox._scout()
        tools = []
        for t in layer["tools"]:
            e = self.toolbox.find(t["name"])
            pub = self.toolbox._public(e, cands)
            tools.append({**t, **{k: pub[k] for k in ("repo", "licence", "caveats",
                                                       "evidence", "next")}})
        return {**layer, "tools": tools}

    def summary(self) -> dict[str, Any]:
        counts = {s: sum(1 for x in self.layers if x["status"] == s) for s in STATUSES}
        order = sorted((x for x in self.layers if x.get("build")), key=lambda x: x["build"])
        return {"checked": self.checked, "counts": counts,
                "layers": [{k: x[k] for k in ("id", "name", "status", "risk")} |
                           {"tools": len(x["tools"])} for x in self.layers],
                "build_order": [{"build": x["build"], "id": x["id"], "name": x["name"],
                                 "next": x.get("next", "")} for x in order],
                "how_to_read": "bau toolbox map --layer ID shows one layer's tools"}


def brief(task: str, home: Path | None = None, toolbox: Toolbox | None = None,
          cmap: CapabilityMap | None = None,
          watch: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    """One task, answered in one place: what BAU has, the gap, researched tools and the
    newest open-source candidates.

    Read-only and offline. It never searches GitHub, installs anything or decides: for a
    live search Jarvis offers ``find_tools``, and the owner still chooses what is added.
    """
    task = (task or "").strip()[:300]
    tb = toolbox or Toolbox(home)
    cm = cmap or CapabilityMap(toolbox=tb)
    layer = cm.match(task) if task else None
    if watch is None:
        from .scout import Scout
        from .scout.watch import shortlist
        watch = shortlist(Scout(home or bau_home()))
    words = set(_terms(task + " " + " ".join(v for s, v in SAY.items()
                                              if s in task.lower())))
    pool = watch.get("test_next", []) + watch.get("watch", [])
    relevant = [i for i in pool if not words or words & set(
        _terms(" ".join([i.get("repo", ""), i.get("claims", ""),
                         " ".join(i.get("categories", []))])))]
    latest = (relevant or pool)[:5]
    plans = {t["name"]: t for t in layer.get("tools", [])} if layer else {}
    researched = []
    for e in tb.ask(task, k=5) if task else []:
        p = plans.get(e["name"])
        researched.append({**e, **({"map_plan": p["plan"], "map_why": p["why"]} if p else {})})
    if layer is None:
        nxt = ("No capability layer matches this task yet: try other words, then search "
               "GitHub with find_tools.")
    elif layer["status"] == "have":
        nxt = (f"BAU already has this ({layer['name']}): use what already_have lists; do "
               "not add a second tool for the same job.")
    else:
        nxt = (layer.get("next")
               or f"{layer['name']} is {layer['status']}: inspect a candidate first.")
    return {
        "task": task,
        "layer": ({k: layer.get(k) for k in ("id", "name", "status", "risk", "build")}
                  if layer else None),
        "already_have": list(layer.get("in_bau", [])) if layer else [],
        "researched": researched,
        "latest": [{k: i.get(k) for k in ("repo", "url", "categories", "claims", "have",
                                          "trend", "new", "created", "opportunity", "next")}
                   for i in latest],
        "latest_note": ("the weekly watch has not run yet: bau scout watch" if not pool
                        else "new = created in the last 90 days"),
        "next": nxt,
        "search": ("find_tools searches GitHub now (latest=true for projects created in "
                   "the last 90 days); nothing is installed or run without the owner."),
    }
