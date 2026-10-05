"""AI content disclosure service (spec §14-16, §77).

Every generated artifact carries a provenance record. Before publication
the "publish" policy domain decides whether a visible label and/or a
machine-readable marking is required, and blocks publication until both
exist. It also blocks if a pipeline step stripped provenance (C2PA / latent
watermark) that the input carried: re-encoding in a media factory is the
usual way this silently breaks EU AI Act Art. 50(2) and California's AI
Transparency Act.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from typing import Any

from . import jurisdiction
from .decision import Decision
from .policy import PolicyEngine

LABELS = {
    "synthetic_performer": "Features an AI-generated (synthetic) performer",
    "voice_clone": "AI-GENERATED VOICE",
    "deepfake": "AI-ALTERED CONTENT - depicts events or people that are not real",
    "video": "AI-GENERATED VIDEO",
    "image": "AI-GENERATED IMAGE",
    "audio": "AI-GENERATED AUDIO",
    "text": "AI-GENERATED",
    "assisted": "AI-ASSISTED",
}


@dataclass
class Provenance:
    artifact_id: str
    media_type: str                    # text | image | video | audio
    ai_generated: bool
    ai_assisted: bool
    human_authored: bool
    human_modified: bool
    model_id: str | None = None
    provider: str | None = None
    generation_timestamp: str | None = None
    generation_job: str | None = None
    source_material: list[str] = field(default_factory=list)
    synthetic_media: bool = False
    deepfake: bool = False
    likeness_used: bool = False
    voice_clone: bool = False
    consent_status: str = "not_required"   # not_required | granted | missing | expired | ambiguous
    input_had_provenance_marking: bool = False
    machine_readable_marking: bool = False
    visible_disclosure_text: str | None = None
    human_contribution: list[str] = field(default_factory=list)

    def suggested_label(self) -> str | None:
        if self.deepfake:
            return LABELS["deepfake"]
        if self.voice_clone:
            return LABELS["voice_clone"]
        if self.ai_generated:
            return LABELS.get(self.media_type, LABELS["text"])
        if self.ai_assisted:
            return LABELS["assisted"]
        return None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def publish_facts(p: Provenance, ctx: dict[str, Any]) -> dict[str, Any]:
    juris: list[str] = []
    for loc in ctx.get("audience", [{"country": None}]):
        juris = jurisdiction.merge(juris, jurisdiction.resolve(loc.get("country"),
                                                               loc.get("region"))[0])
    return {
        "jurisdictions": juris,
        "artifact": {
            "media_type": p.media_type,
            "ai_generated": p.ai_generated,
            "synthetic_media": p.synthetic_media or (p.ai_generated and p.media_type != "text"),
            "deepfake": p.deepfake,
            "likeness_used": p.likeness_used or p.voice_clone,
            "consent_status": p.consent_status,
            "visible_disclosure": bool(p.visible_disclosure_text),
            "machine_readable_marking": p.machine_readable_marking,
            "provenance_preserved": (p.machine_readable_marking
                                     or not p.input_had_provenance_marking),
            "provenance_record": bool(p.model_id or not p.ai_generated),
        },
        "context": {
            "is_advertisement": ctx.get("is_advertisement", False),
            "synthetic_performer": ctx.get("synthetic_performer", False),
            "audio_only": p.media_type == "audio",
            "public_interest_text": ctx.get("public_interest_text", False),
            "human_editorial_responsibility": ctx.get("human_editorial_responsibility", False),
            "is_review_or_testimonial": ctx.get("is_review_or_testimonial", False),
            "platform_requires_ai_label": ctx.get("platform_requires_ai_label"),
            "platform_label_set": ctx.get("platform_label_set"),
            # child-directed content (bau.kids): rules skip unless child_directed
            "child_directed": ctx.get("child_directed", False),
            "made_for_kids_set": ctx.get("made_for_kids_set"),
            "collects_child_data": ctx.get("collects_child_data"),
            "commercial_pressure": ctx.get("commercial_pressure"),
            "paid_promotion": ctx.get("paid_promotion", False),
            "unsuitable_for_kids": ctx.get("unsuitable_for_kids"),
            "unlicensed_characters": ctx.get("unlicensed_characters"),
            "near_duplicate": ctx.get("near_duplicate"),
        },
    }


def check_publication(p: Provenance, ctx: dict[str, Any], engine: PolicyEngine,
                      on: dt.date | None = None) -> Decision:
    return engine.evaluate("publish", publish_facts(p, ctx), on=on or dt.date.today())


def chatbot_facts(ctx: dict[str, Any]) -> dict[str, Any]:
    juris: list[str] = []
    for loc in ctx.get("audience", [{"country": None}]):
        juris = jurisdiction.merge(juris, jurisdiction.resolve(loc.get("country"),
                                                               loc.get("region"))[0])
    return {"jurisdictions": juris, "bot": {
        "discloses_ai_at_start": ctx.get("discloses_ai_at_start"),
        "companion": ctx.get("companion", False),
        "minor_possible": ctx.get("minor_possible", True),
        "human_handoff_minutes": ctx.get("human_handoff_minutes"),
        "operator_revenue_usd": ctx.get("operator_revenue_usd"),
    }}
