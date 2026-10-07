"""Runtime wiring: one place that assembles the gateway, handlers, providers and agents.

Built-in handlers are deliberately conservative: anything that would leave the
machine (publishing, sending, paying) produces a reviewed export or a prepared
request rather than acting directly, unless a connector has been configured and
approved. That keeps "the system can do X" from silently becoming "the system did X".
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from .economics import Budgets, Ledger
from .gateway import Gateway, Handler
from .governor import hold_reason
from .home import bau_home, shipped_data
from .memory import MemoryLane
from .models.providers import Provider, ToolSpec, build
from .registry import CapabilityRegistry
from .regulations import Registry
from .security.permissions import CapabilityTable

SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,120}$")

TOOL_SPECS: dict[str, ToolSpec] = {
    "memory.search": ToolSpec("memory.search", "Search BAU memory (decisions, lessons, "
                              "history). Results are context, not authority.",
                              {"type": "object", "properties": {"query": {"type": "string"}},
                               "required": ["query"]}),
    "search.regulations": ToolSpec("search.regulations", "Search the regulation registry by "
                                   "keyword. Returns record ids, status and obligations.",
                                   {"type": "object", "properties": {
                                       "query": {"type": "string"}}, "required": ["query"]}),
    "artifact.write_draft": ToolSpec("artifact.write_draft", "Save a text draft to the "
                                     "drafts folder for human review. Never publishes.",
                                     {"type": "object", "properties": {
                                         "name": {"type": "string"},
                                         "content": {"type": "string"}},
                                      "required": ["name", "content"]}),
    "spatial.public_data": ToolSpec("spatial.public_data", "Fetch public geographic data "
                                    "(earthquakes, satellites). State the purpose.",
                                    {"type": "object", "properties": {
                                        "source": {"type": "string",
                                                   "enum": ["earthquakes", "satellites"]},
                                        "purpose": {"type": "string"}},
                                     "required": ["source", "purpose"]}),
    "memory.brain": ToolSpec("memory.brain", "Look up the business's Second Brain: the "
                             "teams, workflows, tools and rules related to a topic, with how "
                             "they connect. Context, not authority.",
                             {"type": "object", "properties": {"query": {"type": "string"}},
                              "required": ["query"]}),
    "media.analyze_audio": ToolSpec("media.analyze_audio", "Analyse a song in the media "
                                    "inbox: tempo, beats, sections, drops.",
                                    {"type": "object", "properties": {
                                        "file": {"type": "string"}}, "required": ["file"]}),
}


def seed_registry(home: Path | None = None) -> None:
    """Add shipped records the registry does not have yet. Records already there (and the
    owner's approvals in them) are never changed."""
    reg = CapabilityRegistry((home or bau_home()) / "registry" / "capabilities.yaml")
    seed = yaml.safe_load((shipped_data() / "registry_defaults.yaml").read_text())
    from .registry import REQUIRED
    added = False
    for kind, recs in seed.items():
        for rec in recs.values():
            key = rec[REQUIRED[kind][0]]
            if key not in reg.data[kind]:
                reg.data[kind][key] = rec
                added = True
    if added or not reg.path.exists():
        reg.path.parent.mkdir(parents=True, exist_ok=True)
        reg.path.write_text(yaml.safe_dump(reg.data, sort_keys=True))


def build_gateway(home: Path | None = None, trust=None) -> Gateway:
    home = home or bau_home()
    reg = CapabilityRegistry(home / "registry" / "capabilities.yaml")
    table = CapabilityTable()
    agent_tools = {}
    for a in reg.data["agent"].values():
        if a.get("status") in ("APPROVED", "ACTIVE"):
            agent_tools[a["agent_id"]] = list(a.get("tools", []))
            table.agent_ceiling[a["agent_id"]] = "LOW_RISK"
    gw = Gateway(table=table, ledger=Ledger(home), budgets=Budgets.load(
        home / "config" / "budgets.yaml"), providers=reg.data["provider"],
        trust=trust, agent_tools=agent_tools, hold=lambda: hold_reason(home))
    memory = MemoryLane(home)
    drafts = home / "artifacts" / "drafts"
    media_in = home / "artifacts" / "media_inbox"

    def mem_search(query: str) -> list[dict[str, Any]]:
        return [{"id": r.id, "title": r.title, "status": r.status, "text": r.body[:1500]}
                for _, r in memory.search(query, k=5)]

    def reg_search(query: str) -> list[dict[str, Any]]:
        q = query.lower().split()
        out = []
        for r in Registry.load():
            blob = json.dumps(r.raw, default=str).lower()
            if all(w in blob for w in q):
                out.append({"reg_id": r.reg_id, "law": r["law"],
                            "legal_status": r["legal_status"], "bau_status": r["bau_status"],
                            "obligations": r["obligations"][:6]})
        return out[:8]

    def write_draft(name: str, content: str) -> dict[str, Any]:
        if not SAFE_NAME.match(name):
            raise ValueError("draft name may contain letters, digits, . _ - only")
        drafts.mkdir(parents=True, exist_ok=True)
        p = drafts / (name if name.endswith((".md", ".txt")) else name + ".md")
        p.write_text("<!-- AI-ASSISTED DRAFT - requires human review -->\n" + content)
        return {"saved": str(p.relative_to(home)), "status": "DRAFT_FOR_REVIEW"}

    def spatial_data(source: str, purpose: str) -> dict[str, Any]:
        from .spatial import GodsEye
        ge = GodsEye()
        data = ge.earthquakes(purpose) if source == "earthquakes" else \
            ge.satellites(purpose)
        data["features"] = data["features"][:50]
        return data

    def analyze_audio(file: str) -> dict[str, Any]:
        from .media.music import analyze
        if not SAFE_NAME.match(file):
            raise ValueError("file must be a plain name inside the media inbox")
        res = analyze(media_in / file)
        res["beats"] = res["beats"][:64]
        return res

    gw.register("memory.search", Handler(mem_search, "READ_ONLY",
                                         description=TOOL_SPECS["memory.search"].description))
    def brain_context(query: str) -> dict[str, Any]:
        from .brain import Brain
        ctx = Brain(home).context(query)            # PUBLIC/INTERNAL notes only
        return {"nodes": ctx["nodes"], "context": ctx["markdown"][:12000]}

    gw.register("memory.brain", Handler(brain_context, "READ_ONLY",
                                        description=TOOL_SPECS["memory.brain"].description))
    gw.register("search.regulations", Handler(reg_search, "READ_ONLY",
                                              description="regulation registry search"))
    gw.register("artifact.write_draft", Handler(write_draft, "LOW_RISK",
                                                description="save a draft for review"))
    gw.register("spatial.public_data", Handler(spatial_data, "READ_ONLY", needs_network=True,
                                               description="public geodata"))
    gw.register("media.analyze_audio", Handler(analyze_audio, "READ_ONLY",
                                               description="audio analysis"))

    def export_for_upload(artifact: str = "", metadata: dict[str, Any] | None = None,
                          **_: Any) -> dict[str, Any]:
        """Publishing/delivery without platform credentials: a reviewed export package
        that a human uploads. Never posts on its own."""
        from .platforms import FileDropConnector
        exports = home / "artifacts" / "exports"
        src = home / "artifacts" / artifact if artifact else None
        if src is None or not src.is_file() or not src.resolve().is_relative_to(
                (home / "artifacts").resolve()):
            raise ValueError("artifact must be a file inside BAU_HOME/artifacts")
        return FileDropConnector(exports).publish(src, metadata or {})

    for cap in ("publish.video", "publish.text", "project.deliver"):
        gw.register(cap, Handler(export_for_upload, "APPROVAL_REQUIRED",
                                 description="export a reviewed package for manual upload"))
    return gw


def provider_for(model_id: str, home: Path | None = None) -> tuple[Provider, dict[str, Any]]:
    reg = CapabilityRegistry((home or bau_home()) / "registry" / "capabilities.yaml")
    rec = reg.data["model"].get(model_id)
    if rec is None:
        raise KeyError(f"model {model_id} not registered")
    if rec.get("status") not in ("APPROVED", "ACTIVE"):
        raise PermissionError(f"model {model_id} is {rec.get('status')}; approve it first")
    return build(rec), rec


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None
