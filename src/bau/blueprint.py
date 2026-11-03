"""Blueprints: understand a GitHub project from the site, without downloading it
(docs/AUTOPILOT.md). The owner's ask (2026-11-02): read the blueprints already sitting on
GitHub - the file tree, README, manifests, latest release - and say what a project is, how it
is built, and how BAU could use it or build its own.

Only GitHub's read-only REST calls are used (facts and dates in scout/github.py). Nothing is
cloned, installed or run. The README is someone else's text: it reaches a model only inside
``agents.untrusted()`` and never appears on the owner's card.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

from .audit import AuditLog

NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MANIFESTS = ("pyproject.toml", "package.json", "requirements.txt", "Cargo.toml", "go.mod",
             "Dockerfile")
HEAVY = {"torch": "a GPU helps (PyTorch)", "tensorflow": "a GPU helps (TensorFlow)",
         "jax": "a GPU helps (JAX)", "cuda": "NVIDIA CUDA", "onnxruntime-gpu": "a GPU"}


def _deps(path: str, text: str) -> tuple[list[str], list[str]]:
    """Dependency names and entry points from one manifest."""
    deps: list[str] = []
    entries: list[str] = []
    name = lambda d: re.split(r"[<>=!~;\[ ]", d.strip(), maxsplit=1)[0].lower()  # noqa: E731
    try:
        if path == "pyproject.toml":
            p = tomllib.loads(text)
            proj = p.get("project", {})
            deps = [name(d) for d in proj.get("dependencies", [])]
            entries = list(proj.get("scripts", {}))
        elif path == "package.json":
            p = json.loads(text)
            deps = [d.lower() for d in {**p.get("dependencies", {}),
                                        **p.get("peerDependencies", {})}]
            b = p.get("bin")
            entries = list(b) if isinstance(b, dict) else [p.get("name", "")] if b else []
        elif path == "requirements.txt":
            deps = [name(x) for x in text.splitlines() if x.strip() and not
                    x.lstrip().startswith(("#", "-"))]
    except (ValueError, tomllib.TOMLDecodeError, AttributeError):
        pass
    return [d for d in deps if d], [e for e in entries if e]


def _kind(deps: list[str], paths: list[str], docker: str, entries: list[str]) -> str:
    # what the project ships, not its tests' fakes and examples
    low = [p.lower() for p in paths if not re.search(r"(^|/)(tests?|fixtures|examples?)/",
                                                      p.lower())]
    if any(d in ("mcp", "fastmcp", "@modelcontextprotocol/sdk") for d in deps) or \
            any(re.search(r"mcp[_-]?server|server[_-]?mcp", p.rsplit("/", 1)[-1]) for p in low):
        return "mcp server"
    if "expose" in docker.lower():
        return "service"
    if entries:
        return "command-line tool"
    # a skills collection with no program of its own (a project that ships code and also
    # some skills, like BAU, is the program; real read 2026-11-02)
    if any(p.endswith("skill.md") for p in low) and not deps:
        return "agent skill"
    return "library"


USE = {
    "mcp server": "plug it into Jarvis as an MCP server through the gateway, in its own "
                  "sandbox container on this computer",
    "agent skill": "add it as a text-only skill to an agent folder (bau agents add-skill)",
    "service": "run it in its own container on 127.0.0.1 and talk to it through an adapter "
               "behind the gateway, after a sandbox test",
    "command-line tool": "call it from an adapter behind the gateway, inside the sandbox",
    "library": "wrap it in a small adapter behind the gateway, after a sandbox test",
}


def read(home: Path, full_name: str, gh: Any) -> dict[str, Any]:
    if not NAME.match(full_name) or ".." in full_name:
        raise ValueError("give the repository as OWNER/NAME")
    meta = gh.repo(full_name)
    t = gh.tree(full_name, meta.get("default_branch") or "main")
    blobs = [i for i in t.get("tree", []) if i.get("type") == "blob"]
    paths = [i["path"] for i in blobs]
    deps: list[str] = []
    entries: list[str] = []
    docker = ""
    for m in MANIFESTS:
        if m in paths:
            text = gh.file(full_name, m)
            if m == "Dockerfile":
                docker = text
            d, e = _deps(m, text)
            deps += d
            entries += e
    top = Counter(p.split("/", 1)[0] for p in paths if "/" in p)
    layout = [{"dir": d, "files": n} for d, n in top.most_common(8)]
    kind = _kind(deps, paths, docker, entries)
    rel = gh.latest_release(full_name) or {}
    needs = sorted({v for d in deps for k, v in HEAVY.items() if d.startswith(k)})
    if docker:
        needs.append("Docker or Podman (it ships a Dockerfile)")
    from .agents import untrusted
    readme = gh.readme(full_name)
    lic = (meta.get("license") or {}).get("spdx_id") or "unknown"
    bp = {
        "repo": meta.get("full_name", full_name), "read_at": dt.datetime.now(dt.UTC).isoformat(
            timespec="seconds"),
        "what": (meta.get("description") or "")[:300], "language": meta.get("language"),
        "stars": meta.get("stargazers_count"), "pushed": meta.get("pushed_at"),
        "archived": bool(meta.get("archived")), "topics": meta.get("topics", [])[:10],
        "licence": lic, "release": rel.get("tag_name"), "files": len(paths),
        "tree_cut": bool(t.get("truncated")),
        "tests": any(re.search(r"(^|/)(tests?|spec)/|_test\.|test_", p) for p in paths),
        "docs": any(p.startswith("docs/") or p.lower().startswith("readme") for p in paths),
        "layout": layout, "dependencies": sorted(set(deps))[:40],
        "entry_points": entries[:10], "kind": kind, "how_bau_uses_it": USE[kind],
        "needs": needs,
        "build_our_own": [f"{x['dir']}/: {x['files']} files" for x in layout[:5]],
        "readme_for_models": untrusted(f"github:{full_name}:README", readme)[0],
    }
    out = home / "scout" / "blueprints" / f"{full_name.replace('/', '__')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bp, indent=1))
    AuditLog(home / "audit" / "chain.jsonl").append(
        "scout.blueprint", "autopilot", {"repo": bp["repo"], "kind": kind, "files": len(paths)})
    return bp


def summary(bp: dict[str, Any]) -> str:
    """The owner's card: facts only, never the README's own words."""
    lines = [f"{bp['repo']}: {bp['what']}",
             f"{bp['kind']} in {bp['language']}, {bp['files']} files"
             + (" (GitHub sent only part of a very large tree)" if bp["tree_cut"] else "")
             + f", licence {bp['licence']}" + (f", release {bp['release']}" if bp["release"]
                                                else ""),
             "Built as: " + ", ".join(bp["build_our_own"]) if bp["build_our_own"] else "",
             f"How BAU could use it: {bp['how_bau_uses_it']}."]
    if bp["needs"]:
        lines.append("Needs: " + "; ".join(bp["needs"]))
    lines.append(("Has tests" if bp["tests"] else "No tests found")
                 + (" and docs." if bp["docs"] else ", no docs."))
    if bp["archived"]:
        lines.append("Archived by its owner: no longer maintained.")
    return "\n".join(x for x in lines if x)
