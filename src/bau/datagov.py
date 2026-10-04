"""Data governance: objects, use rights, provider boundary, tracking (spec §17-18, §26, §82-83).

Viewing, storing, embedding, training and commercializing are different rights
(spec §82). Nothing leaves the machine unless the data class, the provider's
terms and the recorded use rights all allow it (spec §83, §101). Unknown -> BLOCK.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from .home import bau_home
from .store import YamlStore

CLASSES = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "PERSONAL", "SENSITIVE_PERSONAL", "FINANCIAL",
           "AUTHENTICATION", "HEALTH", "CHILD_MINOR", "BIOMETRIC", "LEGAL", "TRADE_SECRET",
           "CRITICAL"]
USES = ["view", "store", "process", "index", "embed", "inference", "train", "share",
        "commercialize"]
# Classes that never leave the machine, whatever a provider promises.
LOCAL_ONLY = {"AUTHENTICATION", "CRITICAL", "BIOMETRIC", "CHILD_MINOR"}
# Classes that may go only to providers with no retention and no training.
RESTRICTED = {"SENSITIVE_PERSONAL", "HEALTH", "FINANCIAL", "TRADE_SECRET", "LEGAL",
              "CONFIDENTIAL"}
REQUIRED_FIELDS = ["data_id", "source", "owner", "category", "sensitivity", "purpose",
                   "lawful_basis", "retention_days", "location", "uses_allowed"]


class DataRegistry:
    def __init__(self, path: Path | None = None):
        self.store = YamlStore(path or (bau_home() / "data" / "objects.yaml"),
                               {"objects": {}})

    def register(self, rec: dict[str, Any]) -> dict[str, Any]:
        missing = [k for k in REQUIRED_FIELDS if k not in rec]
        if missing:
            raise ValueError(f"missing fields: {missing}")
        if rec["sensitivity"] not in CLASSES:
            raise ValueError(f"sensitivity must be one of {CLASSES}")
        bad = [u for u in rec["uses_allowed"] if u not in USES]
        if bad:
            raise ValueError(f"unknown uses {bad}")
        if rec["sensitivity"] in ("PERSONAL", "SENSITIVE_PERSONAL", "HEALTH", "CHILD_MINOR",
                                  "BIOMETRIC") and not rec.get("lawful_basis"):
            raise ValueError("personal data needs a lawful basis")
        rec = dict(rec)
        rec.setdefault("collected_at", dt.date.today().isoformat())
        data = self.store.load()
        data["objects"][rec["data_id"]] = rec
        self.store.save(data)
        return rec

    def get(self, data_id: str) -> dict[str, Any] | None:
        return self.store.load()["objects"].get(data_id)

    def may(self, data_id: str, use: str) -> tuple[bool, str]:
        rec = self.get(data_id)
        if rec is None:
            return False, "data object not registered - unknown data is not usable"
        if use not in USES:
            return False, f"unknown use {use}"
        if use not in rec["uses_allowed"]:
            return False, f"{use} not among recorded rights {rec['uses_allowed']}"
        return True, ""

    def expired(self, on: dt.date | None = None) -> list[dict[str, Any]]:
        """Data past its retention period: delete when the purpose ends (spec §18)."""
        on = on or dt.date.today()
        out = []
        for rec in self.store.load()["objects"].values():
            start = dt.date.fromisoformat(str(rec["collected_at"]))
            if rec.get("legal_hold"):
                continue
            if start + dt.timedelta(days=int(rec["retention_days"])) < on:
                out.append(rec)
        return out


def provider_allows(provider: dict[str, Any] | None, classes: list[str]) -> tuple[bool, str]:
    """Provider boundary (spec §83): may these data classes be sent to this provider?"""
    if not classes:
        return False, "data classification missing - unknown is blocked (spec §101)"
    unknown = [c for c in classes if c not in CLASSES]
    if unknown:
        return False, f"unknown data classes {unknown}"
    if provider is None:
        return False, "provider not registered"
    if provider.get("status") not in ("APPROVED", "ACTIVE"):
        return False, f"provider status {provider.get('status')} is not approved"
    local = provider.get("jurisdiction") == "local" or provider.get("data_retained") == "local"
    if local:
        return True, "local provider"
    hard = sorted(set(classes) & LOCAL_ONLY)
    if hard:
        return False, f"{hard} never leave the machine"
    if set(classes) & RESTRICTED:
        if provider.get("data_retained") not in ("none", "zero"):
            return False, "restricted data needs a zero-retention provider"
        if provider.get("training_on_customer_data") is not False:
            return False, "restricted data needs a provider that does not train on it"
    if "PERSONAL" in classes and provider.get("training_on_customer_data") is not False:
        return False, "personal data cannot go to a provider that trains on it"
    if ("PERSONAL" in classes or set(classes) & RESTRICTED) and not provider.get("dpa_signed"):
        return False, "personal/restricted data needs a signed data processing agreement"
    return True, ""


class TrackingRegistry:
    """Cookies, pixels, SDKs, analytics, ad tech (spec §26)."""

    KINDS = {"cookie", "pixel", "sdk", "analytics", "ad_tech", "tracking"}

    def __init__(self, path: Path | None = None):
        self.store = YamlStore(path or (bau_home() / "data" / "tracking.yaml"), {"items": {}})

    def add(self, name: str, kind: str, collects: list[str], purpose: str, recipient: str,
            retention_days: int, strictly_necessary: bool, can_disable: bool) -> dict[str, Any]:
        if kind not in self.KINDS:
            raise ValueError(f"kind must be one of {sorted(self.KINDS)}")
        rec = {"name": name, "kind": kind, "collects": collects, "purpose": purpose,
               "recipient": recipient, "retention_days": retention_days,
               "strictly_necessary": strictly_necessary, "can_disable": can_disable,
               # Strictly-necessary items aside, assume consent/opt-out is required
               # until counsel says otherwise for the target jurisdiction.
               "consent_or_opt_out_required": not strictly_necessary}
        data = self.store.load()
        data["items"][name] = rec
        self.store.save(data)
        return rec

    def report(self) -> dict[str, Any]:
        items = list(self.store.load()["items"].values())
        return {"items": items,
                "problems": [i["name"] for i in items
                             if not i["strictly_necessary"] and not i["can_disable"]]}
