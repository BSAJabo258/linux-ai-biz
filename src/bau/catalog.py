"""The tool catalog (Phase 2 of the universal automation upgrade, 2026-11-11): one record per
tool, joined from what BAU already keeps apart - the toolbox (researched, ``data/toolbox.yaml``),
Repo Scout (found, inspected in quarantine, licence and security gates), the open-source watch's
``integrated`` list, the capability registry's MCP servers and their last health check
(``mcp.check``). Nothing is copied: every call reads those stores again.

Each record has one ``state`` from the twelve below, set only by evidence BAU recorded, never by
a project's own claims or by a repository merely existing:

    DISCOVERED         in the toolbox or found by Scout; claims only
    INSPECTED          downloaded into quarantine and scanned (Scout inspect), or QUARANTINED
    LICENSE_VERIFIED   the licence file found in the download allows business use
    SECURITY_REVIEWED  and the static scan found nothing that blocks a sandbox test
    INSTALLED          not recorded by BAU yet: never set
    CONFIGURED         an MCP server record BAU knows how to start (REGISTERED)
    CONNECTED          not recorded by BAU yet: never set
    TESTED             a sandbox test passed (Scout validation)
    APPROVED           the owner approved it (registry APPROVED)
    ENABLED            in use: registry ACTIVE, or on the watch's ``integrated`` list
    DISABLED           registry DEPRECATED
    REVOKED            registry REVOKED (overrides everything)

A field BAU has no evidence for is ``None``, never a guess.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .home import bau_home, shipped_data

STATES = ("DISCOVERED", "INSPECTED", "LICENSE_VERIFIED", "SECURITY_REVIEWED", "INSTALLED",
          "CONFIGURED", "CONNECTED", "TESTED", "APPROVED", "ENABLED", "DISABLED", "REVOKED")
# Registry status -> catalog state (registry.STATUSES).
FROM_REGISTRY = {"UNTRUSTED": "DISCOVERED", "QUARANTINED": "INSPECTED",
                 "REGISTERED": "CONFIGURED", "APPROVED": "APPROVED", "ACTIVE": "ENABLED",
                 "DEPRECATED": "DISABLED", "REVOKED": "REVOKED"}
FIELDS = ("id", "name", "category", "source_repository", "source_url", "version", "commit",
          "license", "runtime", "capabilities", "permissions", "network_access",
          "secret_requirements", "health_check", "security_status", "approval_status",
          "provenance", "last_verified")


def _rank(state: str) -> int:
    return STATES.index(state)


def _later(a: str, b: str) -> str:
    """The furthest state the evidence reaches. DISABLED and REVOKED come last in STATES, so
    they win over any other evidence."""
    return a if _rank(a) >= _rank(b) else b


def _blank(rid: str, name: str) -> dict[str, Any]:
    return {**{f: None for f in FIELDS}, "id": rid, "name": name, "state": "DISCOVERED",
            "evidence": [], "provenance": []}


def _repo(url: str) -> str | None:
    u = str(url or "")
    if u.startswith("https://github.com/"):
        parts = u.removeprefix("https://github.com/").strip("/").split("/")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1].removesuffix('.git')}".lower()
    return None


def _scout_state(c: dict[str, Any]) -> tuple[str, list[str]]:
    from .security.sentinel import COMMERCIAL_OK
    ins = c.get("inspected")
    if not ins:
        return "DISCOVERED", ["found by Repo Scout; its description is a claim"]
    state, ev = "INSPECTED", [f"inspected {str(ins.get('at', ''))[:10]} at commit "
                              f"{str(ins.get('commit', ''))[:12]}: {ins.get('verdict')}"]
    lic = c.get("license") or {}
    if lic.get("detected") in COMMERCIAL_OK and lic.get("status") == "COMMERCIAL_OK":
        state = "LICENSE_VERIFIED"
        ev.append(f"licence file: {lic['detected']}")
        if ins.get("verdict") == "ELIGIBLE_FOR_SANDBOX":
            state = "SECURITY_REVIEWED"
    if (c.get("validation") or {}).get("status") == "passed":
        state = _later(state, "TESTED")
        ev.append("sandbox test passed")
    return state, ev


class Catalog:
    def __init__(self, home: Path | None = None, data: Path | None = None):
        self.home = home or bau_home()
        self.data = data or shipped_data()

    def _read(self, path: Path, loader: Any) -> Any:
        try:
            return loader(path.read_text()) or {}
        except (OSError, ValueError, yaml.YAMLError):
            return {}

    def records(self) -> list[dict[str, Any]]:
        from .toolbox import Toolbox
        out: dict[str, dict[str, Any]] = {}

        def get(rid: str, name: str) -> dict[str, Any]:
            return out.setdefault(rid, _blank(rid, name))

        for e in Toolbox(self.home, self.data / "toolbox.yaml").entries:
            r = get(str(e["repo"]).lower(), e["name"])
            r.update(category=e["category"], source_repository=e["repo"], source_url=e["url"],
                     license=e["licence"], capabilities=e["problem"])
            r["provenance"].append(f"toolbox research {e.get('checked') or 'see toolbox.yaml'}"
                                   f": {', '.join(e['sources'][:2])}")
            r["evidence"].append("researched: the project's own claims")
        for c in self._read(self.home / "scout" / "candidates.json", json.loads).values():
            r = get(c["id"], c.get("full_name") or c["id"])
            r.update(source_repository=c.get("full_name"), source_url=c.get("url"))
            r["capabilities"] = r["capabilities"] or (c.get("claimed") or {}).get("description")
            state, ev = _scout_state(c)
            r["state"] = _later(r["state"], state)
            r["evidence"] += ev
            ins = c.get("inspected") or {}
            if ins:
                r.update(commit=ins.get("commit"), security_status=ins.get("verdict"),
                         last_verified=str(ins.get("at", ""))[:10])
                r["license"] = (c.get("license") or {}).get("detected") or r["license"]
                if (ins.get("surfaces") or {}).get("mcp_server"):
                    r["runtime"] = "MCP server (found in its code)"
            r["provenance"].append(f"Repo Scout ({c.get('origin', 'search')})")
        watch = self._read(self.data / "scout_watch.yaml", yaml.safe_load)
        for repo in watch.get("integrated") or []:
            r = get(str(repo).lower(), repo)
            r["state"] = _later(r["state"], "ENABLED")
            r["source_repository"] = r["source_repository"] or repo
            r["evidence"].append("running in BAU (open-source watch, integrated)")
        reg = self._read(self.home / "registry" / "capabilities.yaml", yaml.safe_load)
        health = self._read(self.home / "mcp" / "health.json", json.loads)
        for sid, rec in (reg.get("mcp") or {}).items():
            r = get(_repo(rec.get("source")) or f"mcp:{sid}", sid)
            r["state"] = _later(r["state"], FROM_REGISTRY.get(rec.get("status"), "DISCOVERED"))
            r.update(version=rec.get("version"), approval_status=rec.get("status"),
                     runtime="MCP server", permissions=rec.get("permissions"),
                     network_access=rec.get("network"),
                     secret_requirements=rec.get("credentials"),
                     source_url=r["source_url"] or rec.get("source"))
            r["license"] = r["license"] or rec.get("license")
            r["evidence"].append(f"registry: mcp/{sid} {rec.get('status')}")
            h = health.get(sid)
            if h:
                r["health_check"] = {k: h.get(k) for k in ("at", "ok", "tools", "changed",
                                                           "error")}
                r["last_verified"] = str(h.get("at", ""))[:10]
            r["provenance"].append(f"capability registry, reviewed by "
                                   f"{rec.get('reviewed_by') or 'nobody yet'}")
        return sorted(out.values(), key=lambda r: (-_rank(r["state"]), r["name"].lower()))

    def find(self, query: str = "", state: str = "") -> list[dict[str, Any]]:
        words = [w for w in query.lower().split() if w]
        if state and state.upper() not in STATES:
            raise ValueError(f"state must be one of {', '.join(STATES)}")
        rows = []
        for r in self.records():
            if state and r["state"] != state.upper():
                continue
            text = " ".join(str(r[k] or "") for k in ("id", "name", "category",
                                                      "capabilities")).lower()
            if all(w in text for w in words):
                rows.append(r)
        return rows

    def show(self, rid: str) -> dict[str, Any]:
        key = rid.strip().lower()
        hit = next((r for r in self.records()
                    if key in (r["id"], r["name"].lower())), None)
        if hit is None:
            raise KeyError(f"{rid} is not in the catalog: `bau catalog` lists what is")
        return hit

    def summary(self) -> dict[str, Any]:
        rows = self.records()
        return {"counts": {s: n for s in STATES
                           if (n := sum(1 for r in rows if r["state"] == s))},
                "in_use": [r["name"] for r in rows if r["state"] == "ENABLED"],
                "approved": [r["name"] for r in rows if r["state"] == "APPROVED"],
                "never_set": "INSTALLED and CONNECTED: BAU records no evidence for them yet"}
