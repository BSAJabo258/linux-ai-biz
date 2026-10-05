"""Capability registry: models, agents, MCP servers, repositories, providers (spec §43-51, §83).

Everything installed is a capability with a declared kind, trust level and
status. Required fields per kind come straight from the spec. A record that
is missing required fields cannot be registered, and only APPROVED/ACTIVE
capabilities may be routed to.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .home import bau_home

REQUIRED: dict[str, list[str]] = {
    "model": ["model_id", "name", "version", "provider", "source", "license", "commercial_use",
              "deployment", "trust_level", "privacy", "status"],
    "agent": ["agent_id", "version", "purpose", "model", "permissions", "budget_usd_per_day",
              "network_scope", "tools", "approval_policy", "risk_level", "status"],
    "mcp": ["mcp_id", "version", "source", "license", "tools", "permissions", "network",
            "data_access", "credentials", "risk", "sandbox", "status"],
    "repository": ["repo_id", "url", "commit", "license", "intake_state", "status"],
    "provider": ["provider_id", "data_sent", "data_retained", "training_on_customer_data",
                 "jurisdiction", "commercial_rights", "terms_url", "status"],
}
STATUSES = {"UNTRUSTED", "QUARANTINED", "REGISTERED", "APPROVED", "ACTIVE", "DEPRECATED",
            "REVOKED"}
TRUST_LEVELS = ["UNKNOWN", "THIRD_PARTY", "ABLITERATED", "MODIFIED", "MERGED", "QUANTIZED",
                "VERIFIED", "OFFICIAL"]
ROUTABLE = {"APPROVED", "ACTIVE"}
# Content lane: an ABLITERATED model may be approved for these jobs ONLY - the
# creative work where a stock model's refusals get in the way of legitimate content.
# It drafts text; it never gets tools, personal data, or any say in a decision.
CONTENT_KINDS = {"creative_writing", "script", "lyrics", "comedy", "ad_copy",
                 "image_prompt", "storyboard"}
CONTENT_LANE = "content_only"


def validate(kind: str, rec: dict[str, Any]) -> list[str]:
    if kind not in REQUIRED:
        return [f"unknown kind {kind}"]
    errs = [f"missing {k}" for k in REQUIRED[kind] if k not in rec]
    if rec.get("status") not in STATUSES:
        errs.append(f"status must be one of {sorted(STATUSES)}")
    if kind == "model":
        if rec.get("trust_level") not in TRUST_LEVELS:
            errs.append(f"trust_level must be one of {TRUST_LEVELS}")
        lane = rec.get("lane") == CONTENT_LANE
        use_for = rec.get("use_for") or []
        if rec.get("status") in ROUTABLE and rec.get("trust_level") in ("UNKNOWN",
                                                                         "THIRD_PARTY"):
            errs.append("unverified models stay isolated (spec §46-47)")
        if rec.get("status") in ROUTABLE and rec.get("trust_level") == "ABLITERATED" \
                and not lane:
            errs.append("abliterated models stay isolated except in the content lane "
                        f"(lane: {CONTENT_LANE}, use_for: some of {sorted(CONTENT_KINDS)})")
        if lane:
            if not use_for or not set(use_for) <= CONTENT_KINDS:
                errs.append(f"content lane use_for must be a non-empty subset of "
                            f"{sorted(CONTENT_KINDS)}")
            if rec.get("deployment") != "local":
                errs.append("content lane models run locally only")
            if rec.get("tools"):
                errs.append("content lane models get no tools")
        if rec.get("status") in ROUTABLE and rec.get("commercial_use") is not True:
            errs.append("commercial routing requires commercial_use: true")
        if rec.get("deployment") == "local" and rec.get("benchmark") is None \
                and rec.get("status") in ROUTABLE:
            errs.append("never fake local availability: local models need a benchmark (spec §6)")
    if kind == "agent" and "root" in (rec.get("permissions") or []):
        errs.append("no agent receives root (spec §7)")
    return errs


class CapabilityRegistry:
    def __init__(self, path: Path | None = None):
        self.path = path or (bau_home() / "registry" / "capabilities.yaml")
        self.data: dict[str, dict[str, dict[str, Any]]] = {k: {} for k in REQUIRED}
        if self.path.exists():
            loaded = yaml.safe_load(self.path.read_text()) or {}
            for k in REQUIRED:
                self.data[k].update(loaded.get(k, {}))

    def add(self, kind: str, rec: dict[str, Any]) -> None:
        errs = validate(kind, rec)
        if errs:
            raise ValueError("; ".join(errs))
        key = rec[REQUIRED[kind][0]]
        self.data[kind][key] = rec
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(yaml.safe_dump(self.data, sort_keys=True))

    def routable(self, kind: str) -> list[dict[str, Any]]:
        return [r for r in self.data[kind].values() if r.get("status") in ROUTABLE]

    def problems(self) -> list[str]:
        out = []
        for kind, recs in self.data.items():
            for key, rec in recs.items():
                out.extend(f"{kind}/{key}: {e}" for e in validate(kind, rec))
        return out
