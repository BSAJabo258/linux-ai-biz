"""ICM workspaces: folder structure as agent architecture (Interpretable Context Methodology,
Van Clief & McDermott, arXiv:2603.16021, MIT; https://github.com/RinDig/icm-architect,
read 2026-10-07).

A workspace is a folder one agent walks. Numbered stage folders carry the order, each
stage's ``CONTEXT.md`` contract lists exactly which files it reads, and outputs are plain
files the owner reads and edits before the next stage runs. BAU adds what ICM leaves
informal: the owner's check is recorded with a SHA-256 of what they checked (edit after
checking and the check is void), kids rules run on the stages that list them, a stage's
context must fit the model, and every draft and check goes into the audit chain.

Layout (template shipped in ``data/workspaces/<name>/``, instance in BAU_HOME):
    <ws>/CLAUDE.md, CONTEXT.md        routing + the pipeline on one screen
    <ws>/_shared/                     factory: fixed for every run (owner edits)
    <ws>/_templates/episode/          the stamp each run is copied from
    <ws>/episodes/ep-NNN-slug/        one run: brief.md + stages/NN_name/{CONTEXT.md,output/}
    <ws>/_index/episodes.md           generated, never edited by hand
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import kids
from .home import bau_home, shipped_data

CHECK_FILE = ".checked"
DEFAULT_BUDGET = 8000          # tokens: ICM's healthy range is 2k-8k per stage
INPUT_RE = re.compile(r"^-\s*(Working|Reference)\s*\([^)]*\):\s*(\S+)\s*$", re.I)
OUTPUT_RE = re.compile(r"^-\s*([\w.-]+)\s*(?:→|->)\s*output/?\s*$")


class WorkspaceError(RuntimeError):
    pass


@dataclass
class Contract:
    stage: str
    path: Path
    job: str
    inputs: list[tuple[str, str]]            # (working|reference, relative path)
    outputs: list[str]
    process: str
    human_check: str
    checks: list[str] = field(default_factory=list)
    agent: bool = True

    @property
    def out_dir(self) -> Path:
        return self.path.parent / "output"


def _sections(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    name = "_head"
    for line in text.splitlines():
        if line.startswith("## "):
            name = line[3:].strip().lower()
            out[name] = ""
        else:
            out[name] = out.get(name, "") + line + "\n"
    return out


def parse_contract(path: Path) -> Contract:
    text = path.read_text()
    sec = _sections(text)
    head = [ln for ln in sec.get("_head", "").splitlines() if ln.strip()]
    job = next((ln for ln in head[1:] if not ln.startswith("#")), "")
    inputs = [(m.group(1).lower(), m.group(2)) for ln in sec.get("inputs", "").splitlines()
              if (m := INPUT_RE.match(ln.strip()))]
    outputs = [m.group(1) for ln in sec.get("outputs", "").splitlines()
               if (m := OUTPUT_RE.match(ln.strip()))]
    checks = [ln.strip()[1:].strip() for ln in sec.get("checks", "").splitlines()
              if ln.strip().startswith("-")]
    if len(outputs) != 1:
        raise WorkspaceError(f"{path}: a stage writes exactly one output file")
    return Contract(stage=path.parent.name, path=path, job=job, inputs=inputs,
                    outputs=outputs, process=sec.get("process", "").strip(),
                    human_check=sec.get("human check", "").strip(), checks=checks,
                    agent="none" not in sec.get("agent", "").lower())


# ------------------------------------------------------------------ instances

def root(home: Path | None = None) -> Path:
    return (home or bau_home()) / "workspaces"


def templates() -> list[str]:
    base = shipped_data() / "workspaces"
    return sorted(p.name for p in base.iterdir() if p.is_dir()) if base.is_dir() else []


def create(template: str, name: str | None = None, home: Path | None = None) -> Path:
    src = shipped_data() / "workspaces" / template
    if not src.is_dir():
        raise WorkspaceError(f"no workspace template {template!r}; have {templates()}")
    dest = root(home) / (name or template)
    if dest.exists():
        raise WorkspaceError(f"{dest} already exists")
    shutil.copytree(src, dest)
    (dest / "episodes").mkdir(exist_ok=True)
    rebuild_index(dest)
    return dest


def open_ws(name: str, home: Path | None = None) -> Path:
    ws = root(home) / name
    if not (ws / "CLAUDE.md").exists():
        raise WorkspaceError(f"no workspace {name!r}: create it with `bau ws create`")
    return ws


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "episode"


def new_episode(ws: Path, idea: str) -> Path:
    eps = ws / "episodes"
    nums = [int(m.group(1)) for p in eps.glob("ep-*") if (m := re.match(r"ep-(\d+)", p.name))]
    ep = eps / f"ep-{max(nums, default=0) + 1:03d}-{_slug(idea)}"
    shutil.copytree(ws / "_templates" / "episode", ep)
    brief = ep / "brief.md"
    brief.write_text(brief.read_text().replace("{{idea}}", idea.strip()))
    for c in (ep / "stages").glob("*/CONTEXT.md"):
        (c.parent / "output").mkdir(exist_ok=True)
    rebuild_index(ws)
    return ep


def find_episode(ws: Path, ep: str) -> Path:
    hits = [p for p in (ws / "episodes").glob(f"{ep}*") if p.is_dir()]
    if len(hits) != 1:
        raise WorkspaceError(f"episode {ep!r}: {'none' if not hits else 'ambiguous'} "
                             f"(have: {', '.join(p.name for p in episodes(ws)) or 'none'})")
    return hits[0]


def episodes(ws: Path) -> list[Path]:
    return sorted(p for p in (ws / "episodes").glob("ep-*") if p.is_dir())


def contracts(ep: Path) -> list[Contract]:
    return [parse_contract(p) for p in sorted((ep / "stages").glob("*/CONTEXT.md"))]


# ------------------------------------------------------------------ state from files

def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_checked(c: Contract) -> bool:
    mark = c.out_dir / CHECK_FILE
    if not mark.exists():
        return False
    try:
        rec = json.loads(mark.read_text())
    except ValueError:
        return False
    return all((c.out_dir / o).exists() and rec.get("sha256", {}).get(o) == _sha(c.out_dir / o)
               for o in c.outputs)


def run_checks(ws: Path, ep: Path, c: Contract) -> list[dict[str, str]]:
    """Problems the stage's listed checks find in its current output (empty = fine)."""
    issues: list[dict[str, str]] = []
    for name in c.checks:
        for o in c.outputs:
            f = c.out_dir / o
            if not f.exists():
                continue
            text = f.read_text()
            if name == "kids_text":
                issues += [i for i in kids.scan("", text) if i["issue"] != "clickbait"]
            elif name == "kids_metadata":
                issues += _metadata_issues(ws, ep, text)
            elif name == "series_lock":
                from .series import Series
                sr = Series(ws)
                # Applies once the owner has filled in the character sheets; until then the
                # series bible alone describes the characters.
                if not sr.problems():
                    issues += sr.drift(text)
            else:
                raise WorkspaceError(f"{c.path}: unknown check {name!r}")
    return issues


def parse_metadata(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        k, sep, v = line.partition(":")
        if sep and k.strip().lower() in ("title", "description", "tags"):
            out[k.strip().lower()] = v.strip()
    return out


def _metadata_issues(ws: Path, ep: Path, text: str) -> list[dict[str, str]]:
    md = parse_metadata(text)
    if not md.get("title"):
        return [{"issue": "no_title", "detail": "metadata needs a 'Title: ...' line"}]
    tags = [t.strip() for t in md.get("tags", "").split(",") if t.strip()]
    issues = kids.scan(md["title"], md.get("description", ""), tags)
    earlier = [(p.name, parse_metadata(m.read_text()).get("title", ""))
               for p in episodes(ws) if p != ep
               for m in p.glob("stages/*/output/metadata.md")]
    dup = kids.near_duplicate(md["title"], earlier)
    if dup:
        issues.append({"issue": "near_duplicate",
                       "detail": f"title is almost the same as {dup} (mass-produced content)"})
    return issues


def status(ws: Path, ep: Path) -> list[dict[str, Any]]:
    rows, prev_ok = [], True
    for c in contracts(ep):
        have = all((c.out_dir / o).exists() for o in c.outputs)
        if have and is_checked(c):
            state = "checked"
        elif have:
            state = "drafted: owner check needed"
        elif prev_ok:
            state = "ready" if c.agent else "yours to do"
        else:
            state = "waiting"
        issues = run_checks(ws, ep, c) if have else []
        rows.append({"stage": c.stage, "state": state, "job": c.job,
                     "issues": [i["detail"] for i in issues]})
        prev_ok = state == "checked"
    return rows


def next_stage(ep: Path) -> Contract | None:
    prev_ok = True
    for c in contracts(ep):
        have = all((c.out_dir / o).exists() for o in c.outputs)
        if not have:
            return c if prev_ok else None
        prev_ok = is_checked(c)
    return None


def rebuild_index(ws: Path) -> None:
    lines = ["# Episodes", "", "Generated by `bau ws`; never edit by hand.", ""]
    for p in episodes(ws):
        title = ""
        for f in (p / "stages").glob("*/output/metadata.md"):
            title = parse_metadata(f.read_text()).get("title", "")
        if not title:
            pitch = next(iter((p / "stages").glob("*/output/pitch.md")), None)
            src = pitch if pitch else p / "brief.md"
            title = next((ln.lstrip("# ").strip() for ln in src.read_text().splitlines()
                          if ln.strip()), "")
        lines.append(f"- {p.name}: {title}")
    if len(lines) == 4:
        lines.append("(no episodes yet)")
    (ws / "_index").mkdir(exist_ok=True)
    (ws / "_index" / "episodes.md").write_text("\n".join(lines) + "\n")


# ------------------------------------------------------------------ running a stage

def build_context(ep: Path, c: Contract, budget: int = DEFAULT_BUDGET
                  ) -> tuple[str, str, dict[str, str]]:
    """(system, user, {path: sha256}) for one stage: only the files its contract lists."""
    if not c.agent:
        raise WorkspaceError(f"{c.stage} is the owner's stage, not an agent's")
    parts, hashes = [], {}
    for kind, rel in c.inputs:
        f = (c.path.parent / rel).resolve()
        if not f.is_file():
            raise WorkspaceError(f"{c.stage}: input {rel} does not exist yet")
        text = f.read_text()
        if kind == "reference" and "{{" in text:
            raise WorkspaceError(f"set up {f.name} first: it still has {{{{...}}}} "
                                 "placeholders (see setup/questionnaire.md)")
        hashes[rel] = hashlib.sha256(text.encode()).hexdigest()
        label = "REFERENCE (rules to follow)" if kind == "reference" else "WORKING (work on this)"
        parts.append(f"===== {label}: {f.name} =====\n{text.strip()}\n")
    out = c.outputs[0]
    system = (f"You are doing one stage of a production workspace.\nStage: {c.stage}. "
              f"{c.job}\n\nProcess:\n{c.process}\n\nFollow every REFERENCE file as a rule. "
              f"Reply with only the full contents of {out}: no preamble, no explanation, "
              "no code fences.")
    user = "\n".join(parts)
    tokens = (len(system) + len(user)) // 4
    if tokens > budget:
        raise WorkspaceError(f"{c.stage} needs about {tokens} tokens of context, over this "
                             f"model's budget of {budget}: shorten the listed files "
                             "(the series bible is the usual culprit)")
    return system, user, hashes


def _clean(text: str) -> str:
    text = text.strip()
    m = re.fullmatch(r"```[\w-]*\n(.*)\n```", text, re.S)
    return (m.group(1) if m else text).strip() + "\n"


def draft(ws: Path, ep: Path, provider: Any, model: dict[str, Any], audit: Any = None
          ) -> tuple[Contract, Path]:
    """Draft the next stage with the given model. Writes only into that stage's output/."""
    c = next_stage(ep)
    if c is None:
        raise WorkspaceError("nothing to draft: the last output needs your check first "
                             "(`bau ws status` shows which)")
    ctx = int(model.get("context") or DEFAULT_BUDGET * 2)
    system, user, hashes = build_context(ep, c, min(DEFAULT_BUDGET, int(ctx * 0.6)))
    reply = provider.complete(system, [{"role": "user", "content": user}], None,
                              max_tokens=2048)
    if not reply.text.strip():
        raise WorkspaceError(f"{model.get('id')} returned nothing for {c.stage}; try again")
    out = c.out_dir / c.outputs[0]
    c.out_dir.mkdir(exist_ok=True)
    out.write_text(_clean(reply.text))
    if audit is not None:
        audit.append("workspace.drafted", f"model:{model.get('id')}", {
            "workspace": ws.name, "episode": ep.name, "stage": c.stage,
            "inputs": hashes, "output_sha256": _sha(out)})
    rebuild_index(ws)
    return c, out


def check(ws: Path, ep: Path, stage: str, by: str, audit: Any = None) -> Contract:
    """The owner confirms they read (and edited) a stage's output. Human only."""
    if not by.startswith("human:"):
        raise PermissionError("only the owner checks a stage")
    hits = [c for c in contracts(ep) if c.stage == stage or c.stage.startswith(f"{stage}_")]
    if len(hits) != 1:
        raise WorkspaceError(f"no single stage {stage!r} in {ep.name}")
    c = hits[0]
    missing = [o for o in c.outputs if not (c.out_dir / o).exists()]
    if missing:
        raise WorkspaceError(f"{c.stage}: {', '.join(missing)} not written yet")
    issues = run_checks(ws, ep, c)
    if issues:
        raise WorkspaceError(f"{c.stage}: fix these first, then check again: "
                             + "; ".join(i["detail"] for i in issues))
    rec = {"by": by, "at": dt.datetime.now(dt.UTC).isoformat(),
           "sha256": {o: _sha(c.out_dir / o) for o in c.outputs}}
    (c.out_dir / CHECK_FILE).write_text(json.dumps(rec, indent=1) + "\n")
    if audit is not None:
        audit.append("workspace.checked", by, {"workspace": ws.name, "episode": ep.name,
                                               "stage": c.stage, "sha256": rec["sha256"]})
    rebuild_index(ws)
    return c
