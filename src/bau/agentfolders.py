"""Agents as folders: instructions, skills and allowed tools - not a model.

An agent is a folder (shipped in ``data/agents/``, the owner's own in
``BAU_HOME/agents/``, which win on a name clash)::

    shop-researcher/
      AGENT.md            frontmatter: name, description, brain, tools, mcp, skills,
                          max_steps; then the agent's instructions in plain Markdown
      skills/NAME/SKILL.md the agent's own skills (open Agent Skills format)

Shared skills live in ``BAU_HOME/skills/`` and ``data/skills/``; AGENT.md names the ones it
uses. Only each skill's name and description go into the agent's instructions; the agent
opens a skill with the ``inspect.skill`` tool when it needs it (progressive disclosure).

Safety stays where it was: the brain comes from ``brains.py``; every tool call goes through
the gateway, limited to the tools AGENT.md lists; tool results (skills included) reach the
model as untrusted data. The owner approves a folder (``bau agents approve``); the approval
is tied to the folder's exact files, so any change voids it. Community skills come in as
text only: their scripts are never copied or run.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .home import bau_home, shipped_data
from .store import YamlStore
from .workspace import BRAINS

NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_NAME, MAX_DESC = 64, 1024
CLAIMS = re.compile(r"\b(compliant|guarantee[ds]?|risk-free)\b", re.I)
TEXT = (".md", ".txt")
SKILL_TOOL = "inspect.skill"


class AgentFolderError(ValueError):
    """A folder that isn't a readable agent or skill."""


def _front(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        raise AgentFolderError(f"{path}: needs a --- frontmatter block at the top")
    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict):
        raise AgentFolderError(f"{path}: the frontmatter must be key: value lines")
    return meta, m.group(2).strip()


@dataclass
class Skill:
    name: str
    description: str
    path: Path                                    # the skill's folder

    def problems(self) -> list[str]:
        out = []
        if not NAME.match(self.name) or len(self.name) > MAX_NAME:
            out.append(f"skill {self.name!r}: name must be lowercase letters, digits and "
                       f"hyphens, at most {MAX_NAME}")
        if self.name != self.path.name:
            out.append(f"skill {self.name!r}: name must match its folder ({self.path.name})")
        if not self.description or len(self.description) > MAX_DESC:
            out.append(f"skill {self.name!r}: description is required, at most {MAX_DESC}")
        if CLAIMS.search(self.description):
            out.append(f"skill {self.name!r}: no compliance or guarantee claims")
        return out


def _skill(folder: Path) -> Skill:
    meta, _ = _front(folder / "SKILL.md")
    return Skill(str(meta.get("name", "")), str(meta.get("description", "")).strip(), folder)


@dataclass
class Agent:
    name: str
    description: str
    brain: str
    tools: list[str]
    mcp: list[str]
    skill_names: list[str]
    max_steps: int
    instructions: str
    path: Path
    skills: list[Skill] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)

    def purpose(self) -> str:
        lines = [self.instructions]
        if self.skills:
            lines += ["", f"Skills you can open with the {SKILL_TOOL} tool (name: when to "
                      "use it). Open one before doing the work it covers:"]
            lines += [f"- {s.name}: {s.description}" for s in self.skills]
        return "\n".join(lines)


def _dirs(home: Path | None, kind: str) -> list[Path]:
    """Owner's folder first, so their own agents and skills win on a name clash."""
    return [(home or bau_home()) / kind, shipped_data() / kind]


def shipped() -> list[str]:
    base = shipped_data() / "agents"
    return sorted(p.name for p in base.iterdir() if (p / "AGENT.md").is_file())


def names(home: Path | None = None) -> list[str]:
    seen: dict[str, None] = {}
    for d in _dirs(home, "agents"):
        if d.is_dir():
            for p in sorted(d.iterdir()):
                if (p / "AGENT.md").is_file():
                    seen.setdefault(p.name, None)
    return list(seen)


def load(name: str, home: Path | None) -> Agent:
    folder = next((d / name for d in _dirs(home, "agents") if (d / name / "AGENT.md").is_file()),
                  None)
    if folder is None or not NAME.match(name):
        raise AgentFolderError(f"no agent {name!r}; have {', '.join(names(home)) or 'none'}")
    meta, body = _front(folder / "AGENT.md")
    a = Agent(name=str(meta.get("name", "")), description=str(meta.get("description", "")),
              brain=str(meta.get("brain", "strong")), tools=list(meta.get("tools") or []),
              mcp=list(meta.get("mcp") or []), skill_names=list(meta.get("skills") or []),
              max_steps=int(meta.get("max_steps", 8)), instructions=body, path=folder)
    own = sorted(p for p in (folder / "skills").glob("*") if (p / "SKILL.md").is_file())
    found = {p.name: p for p in own}
    for s in a.skill_names:
        if s in found:
            continue
        hit = next((d / s for d in _dirs(home, "skills") if (d / s / "SKILL.md").is_file()),
                   None)
        if hit is None:
            a.missing_skills.append(s)
        else:
            found[s] = hit
    a.skills = [_skill(p) for p in found.values()]
    return a


def problems(a: Agent) -> list[str]:
    from .runtime import TOOL_SPECS
    out = []
    if not NAME.match(a.name) or len(a.name) > MAX_NAME:
        out.append(f"name {a.name!r}: lowercase letters, digits and hyphens, at most "
                   f"{MAX_NAME}")
    if a.name != a.path.name:
        out.append(f"name {a.name!r} must match its folder ({a.path.name})")
    if not a.description or len(a.description) > MAX_DESC:
        out.append(f"description is required, at most {MAX_DESC} characters")
    if a.brain not in BRAINS:
        out.append(f"brain must be one of {', '.join(BRAINS)}")
    if a.brain == "content" and (a.tools or a.mcp):
        out.append("a content-brain agent gets no tools and no MCP servers")
    unknown = [t for t in a.tools if t not in TOOL_SPECS]
    if unknown:
        out.append(f"unknown tools: {', '.join(unknown)} (have {', '.join(TOOL_SPECS)})")
    if not 1 <= a.max_steps <= 30:
        out.append("max_steps must be 1 to 30")
    if CLAIMS.search(a.description) or CLAIMS.search(a.instructions):
        out.append("no compliance or guarantee claims")
    out += [f"skill {s!r} not found (agent's skills/ or the shared skills folders)"
            for s in a.missing_skills]
    for s in a.skills:
        out += s.problems()
    return out


def read_skill(a: Agent, name: str, file: str = "SKILL.md") -> str:
    """The text of one of the agent's skills (or a .md file in its references/)."""
    skill = next((s for s in a.skills if s.name == name), None)
    if skill is None:
        raise KeyError(f"{name!r} is not one of this agent's skills")
    target = (skill.path / file).resolve()
    if not target.is_relative_to(skill.path.resolve()) or target.suffix not in TEXT \
            or not target.is_file():
        raise KeyError(f"{file!r} is not a text file of the {name} skill")
    text = target.read_text()
    if file == "SKILL.md":
        refs = sorted(str(p.relative_to(skill.path)) for p in skill.path.rglob("*")
                      if p.suffix in TEXT and p.name != "SKILL.md")
        if refs:
            text += "\n\nMore in this skill (open with file=...): " + ", ".join(refs)
    return text


# ---------------------------------------------------------------- the owner's approval
def digest(a: Agent) -> str:
    h = hashlib.sha256()
    files = [a.path / "AGENT.md"] + [p for s in a.skills for p in sorted(s.path.rglob("*"))
                                     if p.is_file()]
    for p in files:
        where = p.relative_to(a.path) if p.is_relative_to(a.path) else \
            Path("shared") / p.relative_to(p.parents[1])
        h.update(str(where).encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def _approvals(home: Path) -> YamlStore:
    return YamlStore(home / "config" / "agent_approvals.yaml")


def approval(a: Agent, home: Path | None) -> str:
    rec = (_approvals(home or bau_home()).load() or {}).get(a.name)
    if not rec:
        return "not approved"
    return "approved" if rec.get("sha256") == digest(a) else "changed since approval"


def approve(name: str, by: str, home: Path | None, audit: Any = None) -> dict[str, Any]:
    if not by.startswith("human:"):
        raise PermissionError("only the owner approves an agent")
    home = home or bau_home()
    a = load(name, home)
    probs = problems(a)
    if probs:
        raise AgentFolderError("fix these first: " + "; ".join(probs))
    store = _approvals(home)
    data = store.load() or {}
    data[name] = {"sha256": digest(a), "by": by,
                  "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}
    (home / "config").mkdir(parents=True, exist_ok=True)
    store.save(data)
    if audit is not None:
        audit.append("agentfolder.approved", by, {"agent": name, "sha256": data[name]["sha256"],
                                                  "tools": a.tools, "mcp": a.mcp,
                                                  "skills": [s.name for s in a.skills]})
    return {"agent": name, "approval": "approved", "tools": a.tools, "mcp": a.mcp,
            "skills": [s.name for s in a.skills]}


def summary(a: Agent, home: Path | None) -> dict[str, Any]:
    return {"name": a.name, "description": a.description, "brain": a.brain,
            "tools": a.tools, "mcp": a.mcp, "approval": approval(a, home),
            "skills": [{"name": s.name, "description": s.description} for s in a.skills],
            "problems": problems(a), "folder": str(a.path)}


# ---------------------------------------------------------------- running one
def run(name: str, task: str, home: Path | None, audit: Any = None,
        jarvis: tuple[Any, dict[str, Any]] | None = None, factory: Any = None,
        brains: tuple[Any, dict[str, Any]] | None = None, mission_id: str = "",
        trust: Any = None, double_check: bool = False) -> Any:
    """Run an approved agent folder on one task. ``brains`` forces a (provider, model);
    otherwise an agent on the small brain runs under the team's supervisor."""
    from .audit import AuditLog
    home = home or bau_home()
    a = load(name, home)
    probs = problems(a)
    if probs:
        raise AgentFolderError("; ".join(probs))
    state = approval(a, home)
    if state != "approved":
        raise PermissionError(f"agent {name} is {state}: the owner runs `bau agents approve "
                              f"{name}` after reading its folder")
    audit = audit or AuditLog(home / "audit" / "chain.jsonl")
    if brains is None:
        from .brains import resolve
        b = resolve(a.brain, home, a.path, jarvis or (None, {}), factory,
                    kind="creative_writing" if a.brain == "content" else "")
        if b["brain"] == "small":
            return _supervised(a, task, home, audit, b, jarvis, factory, mission_id, trust,
                               double_check)
        brains = (b["provider"], b["model"])
    return _run_once(a, task, home, audit, brains, mission_id, trust)


def _supervised(a: Agent, task: str, home: Path, audit: Any, boss: dict[str, Any],
                jarvis: Any, factory: Any, mission_id: str, trust: Any,
                double_check: bool) -> Any:
    """The team's boss runs the agent; the supervisor hands a stuck job to the specialist
    (docs/TEAM.md) and the run goes on the score sheet."""
    from . import supervisor, team
    from .brains import resolve
    from .usage import Usage
    chosen = team.show(home)
    mode = chosen["takeover"]
    spec_brain: dict[str, Any] = {}

    def specialist_brain() -> dict[str, Any]:
        if not spec_brain:
            spec_brain.update(resolve("strong", home, a.path, jarvis or (None, {}), factory))
        return spec_brain

    def specialist(t: str) -> Any:
        try:
            s = specialist_brain()
        except (KeyError, PermissionError, ImportError, ValueError) as e:
            from .agents import RunResult
            return RunResult("FAILED", f"the specialist could not start: {e}", 0, [], 0.0, 0)
        audit.append("team.takeover", f"folder:{a.name}",
                     {"from": boss["model"].get("id"), "to": s["model"].get("id"),
                      "task": task[:200]})
        return _run_once(a, t, home, audit,
                         (_metered(s, home, audit, f"folder:{a.name}"), s["model"]),
                         mission_id, trust)

    def verify(answer: str, evidence: list[str]) -> str:
        try:
            s = specialist_brain()
        except (KeyError, PermissionError, ImportError, ValueError) as e:
            return not_checked(e)     # e.g. local only is on and the specialist is Claude
        checker = _metered(s, home, audit, f"folder:{a.name}:check", ledger=True)
        from .agents import untrusted
        msg = (f"Answer to check:\n{answer}\n\n"
               + untrusted("evidence", "\n---\n".join(evidence)[:20000])[0])
        from .models.providers import ProviderError
        try:
            r = checker.complete(
                "Check the answer against the evidence only. Reply OK if every fact in it is "
                "backed by the evidence; otherwise list each fact that is not, in one line "
                "each.", [{"role": "user", "content": msg}], [], 1000)
        except ProviderError as e:             # e.g. the owner's daily limit is reached
            return not_checked(e)
        return (r.text or "").strip() or "no reply"

    res = supervisor.supervise(
        task, lambda t: _run_once(a, t, home, audit,
                                  (_metered(boss, home, audit, f"folder:{a.name}"),
                                   boss["model"]), mission_id, trust),
        specialist if chosen["specialist"] else None, mode=mode,
        over_limit=Usage(home, audit).over_limit,
        verify=verify if double_check and chosen["specialist"] else None)
    team.record(home, team.runs(home, res, boss["model"].get("id") or "",
                                (spec_brain.get("model") or {}).get("id") or "",
                                f"folder:{a.name}"))
    return res


def not_checked(why: Exception) -> str:
    return f"not double-checked: {why}"


def _metered(brain: dict[str, Any], home: Path, audit: Any, who: str,
             ledger: bool = False) -> Any:
    """A brain's provider on the usage meter and held to the owner's daily limits (audit
    2026-10-25: agent-folder runs and the double-check went around it). Agent runs write
    the ledger themselves, so only the double-check writes it here."""
    from .registry import CapabilityRegistry
    from .usage import Metered, Usage
    model = brain["model"]
    mid = model.get("id") or model.get("model_id") or ""

    def price(m: str) -> dict[str, Any]:
        if not m or m == mid:
            return model
        return CapabilityRegistry(home / "registry" / "capabilities.yaml").data["model"].get(
            m) or {}
    return Metered(brain["provider"], Usage(home, audit), price, mid, who, ledger=ledger)


def _run_once(a: Agent, task: str, home: Path, audit: Any,
              brains: tuple[Any, dict[str, Any]], mission_id: str, trust: Any) -> Any:
    from . import agents
    from .gateway import Handler
    from .jobs import JobStore
    from .models.providers import ToolSpec
    from .runtime import TOOL_SPECS, build_gateway
    name = a.name
    provider, model = brains
    gw = build_gateway(home, trust=trust)
    gw.audit = audit
    agent_id = f"folder:{name}"
    specs = dict(TOOL_SPECS)
    specs[SKILL_TOOL] = ToolSpec(SKILL_TOOL, "Open one of your skills by name (file= for a "
                                 "reference file it lists).", {
                                     "type": "object", "properties": {
                                         "name": {"type": "string"},
                                         "file": {"type": "string"}}, "required": ["name"]})
    gw.register(SKILL_TOOL, Handler(lambda name, file="SKILL.md": read_skill(a, name, file),
                                    "READ_ONLY", description="read an agent skill"))
    tools = [*a.tools, SKILL_TOOL] if a.brain != "content" else []
    clients = []
    try:
        if a.mcp:
            from .mcp import attach
            from .registry import CapabilityRegistry
            reg = CapabilityRegistry(home / "registry" / "capabilities.yaml")
            for sid in a.mcp:
                rec = reg.data["mcp"].get(sid)
                if rec is None:
                    raise PermissionError(f"MCP server {sid} is not registered")
                client, extra = attach(gw, rec)
                clients.append(client)
                specs.update(extra)
                tools += list(extra)
        gw.agent_tools[agent_id] = tools
        gw.table.agent_ceiling[agent_id] = "LOW_RISK"
        spec = agents.AgentSpec(agent_id=agent_id, purpose=a.purpose(), tools=tools,
                                model={**model, "model_id": model.get("model_id")
                                       or model.get("id")},
                                max_steps=a.max_steps, tool_specs=specs)
        gw.audit.append("agentfolder.run", agent_id, {"task": task[:200],
                                                      "model": spec.model["model_id"]})
        return agents.run(spec, task, provider, gw, JobStore(home), mission_id=mission_id)
    finally:
        for c in clients:
            c.close()


def new(name: str, home: Path | None, start_from: str = "producer") -> Path:
    """Copy an agent folder to the owner's agents as a new agent to edit (not approved)."""
    home = home or bau_home()
    if not NAME.match(name) or len(name) > MAX_NAME:
        raise AgentFolderError("name: lowercase letters, digits and hyphens, e.g. "
                               "listing-writer")
    src = load(start_from, home)
    dest = home / "agents" / name
    if dest.exists() or name in names(home):
        raise AgentFolderError(f"an agent named {name} already exists")
    shutil.copytree(src.path, dest)
    agent_md = dest / "AGENT.md"
    agent_md.write_text(re.sub(r"^name: .*$", f"name: {name}", agent_md.read_text(), count=1,
                               flags=re.M))
    return dest


# ---------------------------------------------------------------- community skills
def add_skill(src: Path, home: Path | None) -> dict[str, Any]:
    """Copy a downloaded skill folder in as text only (SKILL.md and .md/.txt references).
    Scripts and other files are listed, never copied or run."""
    home = home or bau_home()
    if not (src / "SKILL.md").is_file():
        raise AgentFolderError(f"{src} has no SKILL.md")
    skill = _skill(src)
    probs = [p for p in skill.problems() if "match its folder" not in p]
    if probs:
        raise AgentFolderError("; ".join(probs))
    dest = home / "skills" / skill.name
    if dest.exists():
        raise AgentFolderError(f"a skill named {skill.name} is already in {dest.parent}")
    copied, skipped = [], []
    root = src.resolve()
    for p in sorted(src.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(src)
        inside = p.resolve().is_relative_to(root) and not any(
            q.is_symlink() for q in [p, *p.parents] if q.is_relative_to(src))
        if p.suffix in TEXT and inside:
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dest / rel)
            copied.append(str(rel))
        else:
            skipped.append(str(rel))
    return {"skill": skill.name, "to": str(dest), "copied": copied, "skipped": skipped,
            "note": "text only: scripts were not copied; agents that use it need your "
                    "approval again (bau agents approve NAME)"}
