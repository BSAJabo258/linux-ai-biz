"""Second Brain: the business as a graph of plain Markdown notes you own.

The model is not the memory. Memory is a folder of notes - one per *noun*
(team, tool, workflow, artifact, agent, model, regulation...) - joined by
*verbs* (runs, consumes, produces, uses, owns, governs...). Any model -
Claude, a local model, anything that plugs into the router - reads the same
brain through ``context()``; switching models loses nothing.

* Vault: ``BAU_HOME/brain/`` - Obsidian-compatible (frontmatter + [[wikilinks]]),
  so opening it in Obsidian shows the same graph view as Mission Control.
* Sentences become structure: ``say("Product team runs Slack questions which
  consumes tickets and produces answers")`` creates the nodes and typed edges.
* ``import_system()`` seeds the brain from what BAU already knows: agents,
  models, tools, factories, mission types and their compliance gates.
* ``lint()`` finds what is not yet automatable: workflows without an owner,
  inputs or outputs; broken links; untyped nodes; personal data in notes.
* ``context()`` hands a model only the relevant neighbourhood, and only
  PUBLIC/INTERNAL notes unless the caller allows more.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .home import bau_home
from .memory import tokens

VERBS = ["runs", "consumes", "produces", "uses", "owns", "governs", "requires", "feeds",
         "approves", "monitors", "blocks", "publishes", "sells", "serves"]
# (subject type, object type) a verb implies for nodes that have no type yet
VERB_TYPES: dict[str, tuple[str | None, str | None]] = {
    "runs": ("team", "workflow"), "consumes": ("workflow", "artifact"),
    "produces": ("workflow", "artifact"), "uses": (None, "tool"), "owns": ("team", None),
    "governs": ("governance", None), "approves": ("role", None),
    "publishes": (None, "artifact"), "sells": (None, "product"), "serves": (None, "audience"),
}
TYPES = {"team", "role", "workflow", "artifact", "tool", "agent", "model", "capability",
         "governance", "regulation", "factory", "mission_type", "product", "audience",
         "decision", "metric", "concept"}
CLASS_ORDER = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "PERSONAL", "SENSITIVE_PERSONAL"]
SAFE_FOR_MODELS = ("PUBLIC", "INTERNAL")
STOP = {"the", "a", "an", "our", "my", "its", "their"}
LINK = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
PII = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|(?<![\d-])(\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?"
                 r"[\s.-]?\d{3}[\s.-]?\d{4}(?![\d-])")
MANAGED = ("<!-- bau:relations -->", "<!-- /bau:relations -->")


def slug(text: str) -> str:
    """File-safe id. Keeps '.' and '_' so "publish.video" (capability) and
    "publish_video" (mission type) stay distinct notes; never a path."""
    words = [w.strip("._") for w in re.findall(r"[a-z0-9._]+", text.lower())]
    words = [w for w in words if w]
    while words and words[0] in STOP:
        words.pop(0)
    return "-".join(words)[:80] or "untitled"


@dataclass
class Note:
    id: str
    type: str = "concept"
    title: str = ""
    data_class: str = "INTERNAL"
    status: str = "CURRENT"
    source: str = "owner"                  # owner | system
    relations: dict[str, list[str]] = field(default_factory=dict)
    body: str = ""
    updated: str = ""

    def frontmatter(self) -> dict[str, Any]:
        d = {"id": self.id, "type": self.type, "title": self.title or self.id,
             "data_class": self.data_class, "status": self.status, "source": self.source,
             "updated": self.updated or dt.date.today().isoformat()}
        if self.relations:
            d["relations"] = {v: sorted(set(t)) for v, t in sorted(self.relations.items())
                              if t}
        return d


class Brain:
    def __init__(self, home: Path | None = None):
        self.dir = (home or bau_home()) / "brain"
        self.home = home or bau_home()

    # ------------------------------------------------------------ files
    def path(self, nid: str) -> Path:
        return self.dir / f"{nid}.md"

    def load(self, nid: str) -> Note | None:
        p = self.path(nid)
        return self._parse(p) if p.exists() else None

    @staticmethod
    def _parse(p: Path) -> Note:
        text = p.read_text()
        meta: dict[str, Any] = {}
        body = text
        if text.startswith("---\n"):
            end = text.find("\n---", 4)
            if end != -1:
                meta = yaml.safe_load(text[4:end]) or {}
                body = text[end + 4:].lstrip("\n")
        if MANAGED[0] in body:                       # regenerated on save
            a = body.index(MANAGED[0])
            b = body.find(MANAGED[1])
            body = (body[:a] + (body[b + len(MANAGED[1]):] if b != -1 else "")).strip()
        rel = {v: [str(t) for t in (ts or [])] for v, ts in (meta.get("relations") or {}).items()}
        return Note(id=str(meta.get("id") or p.stem), type=str(meta.get("type", "concept")),
                    title=str(meta.get("title") or p.stem),
                    data_class=str(meta.get("data_class", "INTERNAL")),
                    status=str(meta.get("status", "CURRENT")),
                    source=str(meta.get("source", "owner")), relations=rel, body=body,
                    updated=str(meta.get("updated", "")))

    def save(self, n: Note) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        n.updated = dt.date.today().isoformat()
        lines = [f"- {v} [[{t}]]" for v, ts in sorted(n.relations.items()) for t in sorted(set(ts))]
        managed = f"{MANAGED[0]}\n" + "\n".join(lines) + f"\n{MANAGED[1]}" if lines else ""
        head = f"# {n.title or n.id}\n\n" if not n.body.startswith("# ") else ""
        text = ("---\n" + yaml.safe_dump(n.frontmatter(), sort_keys=False) + "---\n"
                + head + n.body.strip() + ("\n\n" + managed if managed else "") + "\n")
        p = self.path(n.id)
        p.write_text(text)
        return p

    def notes(self) -> dict[str, Note]:
        if not self.dir.exists():
            return {}
        return {n.id: n for n in (self._parse(p) for p in sorted(self.dir.glob("*.md")))}

    def upsert(self, title: str, type_: str | None = None, source: str = "owner",
               data_class: str | None = None, body: str | None = None) -> Note:
        nid = slug(title)
        n = self.load(nid) or Note(id=nid, title=title.strip(), source=source)
        if type_ and (n.type == "concept" or source == "system"):
            n.type = type_ if type_ in TYPES else "concept"
        if data_class:
            n.data_class = data_class
        if body is not None:
            n.body = body
        self.save(n)
        return n

    def relate(self, subj: str, verb: str, obj: str, source: str = "owner") -> None:
        if verb not in VERBS:
            raise ValueError(f"unknown verb {verb!r}; use one of {VERBS}")
        st, ot = VERB_TYPES.get(verb, (None, None))
        s = self.upsert(subj, st, source)
        o = self.upsert(obj, ot, source)
        s = self.load(s.id)
        s.relations.setdefault(verb, [])
        if o.id not in s.relations[verb]:
            s.relations[verb].append(o.id)
        self.save(s)

    # ------------------------------------------------------------ sentences
    def say(self, sentence: str) -> list[tuple[str, str, str]]:
        """Compile a plain-English sentence into typed edges.

        "<A> runs <W> which consumes <X>, <Y> and produces <Z>": a verb after
        "which/that" applies to the previous object; after "and" (or bare) it
        applies to the current subject; objects split on commas and "and"."""
        pat = re.compile(r"\b(" + "|".join(VERBS) + r")\b", re.IGNORECASE)
        parts = pat.split(sentence.strip().rstrip("."))
        if len(parts) < 3:
            raise ValueError(f"no verb found; use one of: {', '.join(VERBS)}")
        subject = parts[0].strip(" ,")
        if not subject:
            raise ValueError("sentence needs a subject before the first verb")
        edges: list[tuple[str, str, str]] = []
        current, last_obj = subject, subject
        for i in range(1, len(parts), 2):
            verb = parts[i].lower()
            phrase = parts[i + 1]
            lead = parts[i - 1].strip().lower()
            if re.search(r"\b(which|that)\s*$", lead):
                current = last_obj
            phrase = re.sub(r"\b(which|that|then)\s*$", "", phrase.strip()).strip(" ,")
            phrase = re.sub(r"\band\s*$", "", phrase).strip(" ,")
            objs = [o.strip() for o in re.split(r",|\band\b", phrase) if o.strip()]
            if not objs:
                raise ValueError(f"'{verb}' needs an object")
            for o in objs:
                self.relate(current, verb, o)
                edges.append((slug(current), verb, slug(o)))
            last_obj = objs[-1]
        return edges

    # ------------------------------------------------------------ graph
    def graph(self) -> dict[str, Any]:
        notes = self.notes()
        nodes = [{"id": n.id, "title": n.title, "type": n.type, "data_class": n.data_class,
                  "status": n.status, "source": n.source} for n in notes.values()]
        edges = []
        for n in notes.values():
            linked = set()
            for verb, targets in n.relations.items():
                for t in targets:
                    edges.append({"source": n.id, "verb": verb, "target": t})
                    linked.add(t)
            for t in {slug(m) for m in LINK.findall(n.body)} - linked - {n.id}:
                edges.append({"source": n.id, "verb": "mentions", "target": t})
        return {"nodes": nodes, "edges": edges}

    def neighbours(self, nid: str, g: dict[str, Any] | None = None) -> set[str]:
        g = g or self.graph()
        return ({e["target"] for e in g["edges"] if e["source"] == nid}
                | {e["source"] for e in g["edges"] if e["target"] == nid})

    def lint(self) -> list[dict[str, str]]:
        notes = self.notes()
        g = self.graph()
        out: list[dict[str, str]] = []
        for e in g["edges"]:
            if e["target"] not in notes:
                out.append({"node": e["source"], "issue": "broken_link",
                            "detail": f"{e['verb']} -> {e['target']} has no note"})
        connected = {e["source"] for e in g["edges"]} | {e["target"] for e in g["edges"]}
        for n in notes.values():
            if n.id not in connected:
                out.append({"node": n.id, "issue": "orphan", "detail": "no relations"})
            if n.type == "concept":
                out.append({"node": n.id, "issue": "untyped",
                            "detail": f"set type to one of {sorted(TYPES)}"})
            if n.data_class not in CLASS_ORDER:
                out.append({"node": n.id, "issue": "data_class",
                            "detail": f"unknown data_class {n.data_class}"})
            if PII.search(n.body) and n.data_class in SAFE_FOR_MODELS:
                out.append({"node": n.id, "issue": "personal_data",
                            "detail": "looks like an email/phone in a note marked "
                                      f"{n.data_class}; remove it or mark the note PERSONAL"})
            if n.type == "workflow":
                runner = [e for e in g["edges"] if e["target"] == n.id and e["verb"] == "runs"]
                missing = [w for w, ok in (("owner (X runs it)", runner),
                                           ("inputs (consumes)", n.relations.get("consumes")),
                                           ("outputs (produces)", n.relations.get("produces")))
                           if not ok]
                if missing:
                    out.append({"node": n.id, "issue": "workflow_incomplete",
                                "detail": "not automatable yet - missing " + ", ".join(missing)})
        return out

    def workflows(self) -> list[dict[str, Any]]:
        g = self.graph()
        cards = []
        for n in self.notes().values():
            if n.type != "workflow":
                continue
            cards.append({"workflow": n.id, "title": n.title,
                          "run_by": sorted(e["source"] for e in g["edges"]
                                           if e["target"] == n.id and e["verb"] == "runs"),
                          "consumes": sorted(n.relations.get("consumes", [])),
                          "produces": sorted(n.relations.get("produces", [])),
                          "uses": sorted(n.relations.get("uses", [])),
                          "governed_by": sorted(e["source"] for e in g["edges"]
                                                if e["target"] == n.id
                                                and e["verb"] == "governs")})
        return cards

    # ------------------------------------------------------------ model context
    def context(self, query: str, hops: int = 1, max_nodes: int = 20,
                allowed: tuple[str, ...] = SAFE_FOR_MODELS) -> dict[str, Any]:
        """The relevant neighbourhood of the graph as plain Markdown for ANY model.
        Notes outside ``allowed`` data classes are never included."""
        notes = {k: v for k, v in self.notes().items() if v.data_class in allowed}
        g = self.graph()
        q = set(tokens(query))
        degree: dict[str, int] = {}
        for e in g["edges"]:
            for k in (e["source"], e["target"]):
                degree[k] = degree.get(k, 0) + 1
        scored = []
        for n in notes.values():
            hay = set(tokens(" ".join([n.id.replace("-", " "), n.type, n.body[:2000]])))
            title_hits = len(q & set(tokens(n.title)))
            hits = len(q & hay)
            if title_hits or hits:
                # title matches count most; ties go to the better-connected note (hubs
                # such as workflows), then to the id for a stable order
                scored.append((-(3 * title_hits + hits + 0.1 * degree.get(n.id, 0)), n.id))
        seeds = [nid for _, nid in sorted(scored)[:5]]
        picked = list(seeds)
        frontier = set(seeds)
        for _ in range(hops):
            nxt = set()
            for nid in frontier:
                nxt |= self.neighbours(nid, g)
            frontier = {x for x in nxt if x in notes and x not in picked}
            picked += sorted(frontier)
        picked = picked[:max_nodes]
        lines = []
        for nid in picked:
            n = notes[nid]
            rel = "; ".join(f"{v} {', '.join(sorted(t))}" for v, t in sorted(n.relations.items()))
            body = "\n".join(ln for ln in n.body.splitlines() if not ln.startswith("# "))
            lines.append(f"## {n.title} ({n.type}, {n.status})\n"
                         + (f"Relations: {rel}\n" if rel else "")
                         + (body[:600].strip() + "\n" if body.strip() else ""))
        withheld = sum(1 for n in self.notes().values() if n.data_class not in allowed)
        return {"query": query, "nodes": picked, "markdown": "\n".join(lines),
                "withheld_by_data_class": withheld}

    # ------------------------------------------------------------ seed from the system
    def import_system(self) -> dict[str, int]:
        """Mirror what BAU already knows into the brain (system notes only; your own
        notes are never overwritten)."""
        from .home import shipped_data
        from .registry import CapabilityRegistry
        before = len(self.notes())
        reg = CapabilityRegistry(self.home / "registry" / "capabilities.yaml")

        def sys_rel(a: tuple[str, str], verb: str, b: tuple[str, str]) -> None:
            for title, typ in (a, b):
                n = self.load(slug(title))
                if n is None or n.source == "system":
                    self.upsert(title, typ, "system")
            self.relate(a[0], verb, b[0], source="system")

        for m in reg.data["model"].values():
            self.upsert(m["model_id"], "model", "system")
        for a in reg.data["agent"].values():
            sys_rel((a["agent_id"], "agent"), "uses", (a["model"], "model"))
            for t in a.get("tools", []):
                sys_rel((a["agent_id"], "agent"), "uses", (t, "capability"))
        local = self.home / "config" / "factories.yaml"
        facs = yaml.safe_load((local if local.exists() else shipped_data() / "factories.yaml")
                              .read_text()) or {}
        for fid, f in facs.items():
            sys_rel((fid, "factory"), "produces", (f["mission_type"], "mission_type"))
            for st in f.get("stages", []):
                if st["type"] == "agent":
                    sys_rel((fid, "factory"), "uses", (st["agent"], "agent"))
                elif st["type"] == "gate":
                    sys_rel((f"{st['domain']} gate", "governance"), "governs", (fid, "factory"))
                elif st["type"] in ("tool", "approval"):
                    sys_rel((fid, "factory"), "requires", (st["capability"], "capability"))
        local = self.home / "config" / "missions.yaml"
        mts = yaml.safe_load((local if local.exists() else shipped_data() / "missions.yaml")
                             .read_text()) or {}
        for mt, spec in mts.items():
            self.upsert(mt, "mission_type", "system")
            for dom in spec.get("requires", []):
                sys_rel((f"{dom} gate", "governance"), "governs", (mt, "mission_type"))
            for cap in spec.get("capabilities", []):
                sys_rel((mt, "mission_type"), "requires", (cap, "capability"))
        return {"notes_before": before, "notes_after": len(self.notes())}

    def export(self, out: Path) -> Path:
        out.write_text(json.dumps(self.graph(), indent=1))
        return out
