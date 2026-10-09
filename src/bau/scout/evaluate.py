"""Evidence, gates and scores for one candidate repository.

Three kinds of fact are kept apart: what the project *claims* (description, topics,
README), what *inspection* found (Sentinel's static scan of the downloaded files), and
what was *verified* by running tests (only the sandbox stage sets that). A score uses
only facts that exist; a missing fact scores nothing and is listed under ``unknowns``.

Licence and security are gates, not points: a candidate whose licence forbids commercial
use, or whose code Sentinel rejects, is blocked however well it scores, and nothing is
eligible to integrate until its licence and security have been reviewed and it has been
tested.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from ..security.sentinel import COMMERCIAL_OK, COPYLEFT, NONCOMMERCIAL

GPU = re.compile(r"\b(cuda|nvidia|gpu|vram|rocm|a100|h100|rtx ?\d{4})\b", re.I)
MODEL_SIZE = re.compile(r"\b(\d{1,3}(?:\.\d)?)\s?b\b(?!yte)", re.I)
KEYS = re.compile(r"\b([A-Z][A-Z0-9]*_(?:API_KEY|TOKEN|SECRET))\b")
INSTALL = {"pip": re.compile(r"\bpip3? install\b|\buv (pip|add)\b|\bpoetry add\b", re.I),
           "npm": re.compile(r"\b(npm|pnpm|yarn) (i|install|add)\b", re.I),
           "docker": re.compile(r"\bdocker(-| )compose\b|\bdocker run\b", re.I),
           "cargo": re.compile(r"\bcargo install\b", re.I),
           "go": re.compile(r"\bgo install\b", re.I)}
NONCOMMERCIAL_TEXT = re.compile(r"non-?commercial|research (use )?only|not for commercial",
                                re.I)


def license_status(spdx: str | None) -> str:
    if not spdx:
        return "UNKNOWN_LICENSE"
    if spdx in NONCOMMERCIAL:
        return "NONCOMMERCIAL_BLOCK"
    if re.sub(r"(-only|-or-later|\+)$", "", spdx) in COPYLEFT:
        return "COPYLEFT_REVIEW"
    if spdx in COMMERCIAL_OK:
        return "COMMERCIAL_OK"
    return "HUMAN_REVIEW"


def readme_signals(text: str) -> dict[str, Any]:
    """What a README says about installing and running it. Claims, not proof."""
    sizes = sorted({float(m) for m in MODEL_SIZE.findall(text) if 0 < float(m) <= 700})
    return {"install": sorted(k for k, rx in INSTALL.items() if rx.search(text)),
            "mentions_gpu": bool(GPU.search(text)),
            "model_sizes_b": sizes[:6],
            "api_keys": sorted(set(KEYS.findall(text)))[:8],
            "says_noncommercial": bool(NONCOMMERCIAL_TEXT.search(text))}


def maintenance(meta: dict[str, Any], cfg: dict[str, Any],
                today: dt.date | None = None) -> str | None:
    if meta.get("archived"):
        return "archived"
    try:
        pushed = dt.date.fromisoformat(str(meta.get("pushed_at"))[:10])
    except ValueError:
        return None
    age = ((today or dt.date.today()) - pushed).days
    return ("active" if age <= cfg["active_days"] else
            "slowing" if age <= cfg["slowing_days"] else "stale")


def integration_method(meta: dict[str, Any], sig: dict[str, Any] | None) -> str | None:
    if not sig:
        return None
    if sig["api_keys"] and not sig["install"]:
        return "external API"
    if "pip" in sig["install"] and (meta.get("language") or "").lower() == "python":
        return "internal library"
    if "docker" in sig["install"]:
        return "separate service"
    if sig["install"]:
        return "external command-line tool"
    return None


def _relevance(cand: dict[str, Any], kw: list[str]) -> float:
    text = " ".join([cand["full_name"], cand["claimed"]["description"],
                     " ".join(cand["claimed"]["topics"])]).lower()
    hits = sum(1 for k in kw if k in text) / max(1, len(kw))
    breadth = min(1.0, len(cand["queries"]) / 3)           # found by several angles
    return round(0.7 * hits + 0.3 * breadth, 2)


def evaluate(cand: dict[str, Any], kw: list[str], cfg: dict[str, Any],
             today: dt.date | None = None) -> dict[str, Any]:
    """Fill scores, gates and unknowns on a candidate record (in place) and return it."""
    meta, sig = cand["metadata"], cand["claimed"].get("readme")
    lic = cand["license"]
    lic["status"] = license_status(lic.get("detected") or lic.get("declared"))
    if sig and sig["says_noncommercial"] and lic["status"] == "COMMERCIAL_OK":
        lic["status"] = "HUMAN_REVIEW"     # README contradicts the declared licence
    cand["maintenance"] = maintenance(meta, cfg, today)
    cand["integration_method"] = integration_method(meta, sig)
    insp = cand.get("inspected") or {}
    if sig or insp:
        heavy = bool(insp.get("heavy_dependencies")) or bool(sig) and (
            sig["mentions_gpu"] or any(x > 8 for x in sig["model_sizes_b"]))
        cand["resources"] = {"gpu_or_large_model": heavy,
                             "api_keys": sig["api_keys"] if sig else [],
                             "from": "code" if insp else "readme claims"}

    sec = cand["security"]["status"]
    val = cand["validation"]["status"]
    s: dict[str, float | None] = {
        "functional_relevance": _relevance(cand, kw),
        "verified_capability": {"passed": 1.0, "failed": 0.0}.get(val),
        "integration_feasibility": {"internal library": 1.0,
                                    "external command-line tool": 0.7,
                                    "separate service": 0.6, "external API": 0.5}.get(
                                        cand["integration_method"] or ""),
        "license": {"COMMERCIAL_OK": 1.0, "COPYLEFT_REVIEW": 0.4, "HUMAN_REVIEW": 0.3,
                    "NONCOMMERCIAL_BLOCK": 0.0}.get(lic["status"]),
        "security": {"ELIGIBLE_FOR_SANDBOX": 1.0, "QUARANTINE_FOR_REVIEW": 0.5,
                     "REJECT_OR_HUMAN_REVIEW": 0.0}.get(sec),
        "resource_compatibility": (None if "resources" not in cand else
                                   0.2 if cand["resources"]["gpu_or_large_model"] else 0.8),
        "maintenance": {"active": 1.0, "slowing": 0.5, "stale": 0.2, "archived": 0.0}.get(
            cand["maintenance"] or ""),
        "business_value": cand.get("business_value"),        # the owner's call
    }
    w = cfg["weights"]
    total_w = sum(w.values())
    cand["scores"] = s
    cand["score"] = round(100 * sum(w[k] * v for k, v in s.items() if v is not None)
                          / total_w, 1)
    cand["evidence_coverage"] = round(100 * sum(w[k] for k, v in s.items() if v is not None)
                                      / total_w)
    cand["unknowns"] = [k for k, v in s.items() if v is None]

    hard, review = [], []
    if lic["status"] == "NONCOMMERCIAL_BLOCK":
        hard.append("licence forbids commercial use")
    elif lic["status"] != "COMMERCIAL_OK":
        review.append(f"licence needs legal review ({lic['status']})")
    elif lic.get("review") != "reviewed":
        review.append("licence declared but not reviewed")
    if sec == "REJECT_OR_HUMAN_REVIEW":
        hard.append("Sentinel found dangerous code, secrets or a blocked licence")
    elif sec == "not reviewed":
        review.append("security not reviewed (bau scout inspect)")
    elif sec == "QUARANTINE_FOR_REVIEW":
        review.append("Sentinel wants a human look (install hooks, binaries or licence)")
    if cand["maintenance"] == "archived":
        hard.append("archived upstream")
    if val == "failed":
        hard.append("failed its tests")
    elif val != "passed":
        review.append("not tested")
    cand["blockers"], cand["needs"] = hard, review
    cand["decision"] = ("rejected" if hard else "eligible" if not review else "needs review")
    return cand
