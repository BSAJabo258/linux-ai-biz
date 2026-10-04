"""Subscriptions and cancellation (spec §22-23, §79).

Legal basis as of 2026-10: the FTC's 2024 "click-to-cancel" amendments were
VACATED (8th Cir., 2025-07-08) and a new ANPRM opened 2026-03-11, so the
enforceable federal law is ROSCA + FTC Act s.5 (the basis of the 2026
Shutterstock $35M settlement), plus state automatic-renewal laws such as
California's (amended by AB 2863, effective 2025-07-01). The controls below
meet the stricter of those, so they do not depend on the rule being revived.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from .. import jurisdiction
from ..decision import Decision
from ..policy import PolicyEngine


def offer_facts(offer: dict[str, Any], customer_country: str | None,
                customer_region: str | None, on: dt.date) -> dict[str, Any]:
    juris, assumed = jurisdiction.resolve(customer_country, customer_region)
    tested = offer.get("cancellation_test_passed_at")
    signup_ch = set(offer.get("signup_channels", []))
    cancel_ch = set(offer.get("cancellation_channels", []))
    consent = offer.get("consent", {})
    trial = offer.get("trial") or {}
    return {
        "jurisdictions": juris,
        "offer": {
            "recurring": offer.get("recurring"),
            "price_disclosed": offer.get("price_disclosed"),
            "billing_frequency_disclosed": offer.get("billing_frequency_disclosed"),
            "renewal_terms_disclosed": offer.get("renewal_terms_disclosed"),
            "total_commitment_disclosed": offer.get("total_commitment_disclosed"),
            "cancellation_fees_disclosed": offer.get("cancellation_fees_disclosed"),
            "material_limitations_disclosed": offer.get("material_limitations_disclosed"),
            "cancellation_method_disclosed": offer.get("cancellation_method_disclosed"),
            "disclosed_before_billing_info": offer.get("disclosed_before_billing_info"),
            "has_trial": bool(trial),
            "trial_end_date_disclosed": trial.get("end_date_disclosed") if trial else True,
            "trial_length_days": trial.get("length_days", 0) if trial else 0,
            "trial_end_reminder": trial.get("reminder_before_end") if trial else True,
            "consent_separate": consent.get("separate_affirmative_action"),
            "consent_prechecked": consent.get("prechecked"),
            "consent_evidence_retained": consent.get("evidence_retained"),
            "acknowledgment_receipt": offer.get("acknowledgment_receipt"),
            "online_cancel_if_online_signup": ("online" in cancel_ch) if "online" in signup_ch
            else True,
            "cancel_not_harder": (offer.get("cancellation_steps") is not None
                                  and offer.get("signup_steps") is not None
                                  and offer["cancellation_steps"] <= offer["signup_steps"])
            if offer.get("cancellation_steps") is not None else None,
            "cancellation_requires_survey": offer.get("cancellation_requires_survey"),
            "save_offers_max": offer.get("save_offers_max"),
            "annual_reminder": offer.get("annual_reminder"),
            "price_change_notice_days": offer.get("price_change_notice_days"),
            "refund_policy_visible": offer.get("refund_policy_visible"),
            "contact_visible": offer.get("contact_visible"),
            "terms_accessible": offer.get("terms_accessible"),
            "privacy_policy_accessible": offer.get("privacy_policy_accessible"),
            "accessibility_tested": offer.get("accessibility_tested"),
            "cancellation_test_age_days": (on - dt.date.fromisoformat(tested)).days
            if tested else None,
        },
        "customer": {"jurisdiction_assumed": assumed},
    }


def check_offer(offer: dict[str, Any], engine: PolicyEngine, customer_country: str | None = None,
                customer_region: str | None = None, on: dt.date | None = None) -> Decision:
    on = on or dt.date.today()
    return engine.evaluate("subscription", offer_facts(offer, customer_country,
                                                       customer_region, on), on=on)


# ---- cancellation state machine -------------------------------------------------

ORDER = ["OPEN", "AUTHENTICATED", "CANCELLED", "CONFIRMED", "BILLING_STOPPED", "RECEIPT_SENT",
         "RECORDED"]
FORBIDDEN = {"phone_only", "email_only", "mandatory_survey", "repeated_save_offer",
             "hidden_setting", "fake_error", "chat_only"}


class CancellationError(RuntimeError):
    pass


@dataclass
class Cancellation:
    subscription_id: str
    state: str = "OPEN"
    save_offers_shown: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    def _go(self, to: str, **detail: Any) -> None:
        if ORDER.index(to) != ORDER.index(self.state) + 1:
            raise CancellationError(f"{self.state} -> {to} is out of order")
        self.state = to
        self.history.append({"state": to, "at": dt.datetime.now(dt.UTC).isoformat(),
                             **detail})

    def obstacle(self, kind: str) -> None:
        """Any obstacle in FORBIDDEN is a defect, never a business choice."""
        if kind in FORBIDDEN:
            raise CancellationError(f"forbidden cancellation obstacle: {kind}")

    def offer_save(self, customer_asked_for_offers: bool = False) -> None:
        # One save offer at most, and none after the customer declines (CA ARL as amended).
        if self.save_offers_shown >= 1 and not customer_asked_for_offers:
            self.obstacle("repeated_save_offer")
        self.save_offers_shown += 1

    def authenticate(self, method: str) -> None:
        self._go("AUTHENTICATED", method=method)

    def cancel(self) -> None:
        self._go("CANCELLED")

    def confirm(self, confirmation_id: str) -> None:
        self._go("CONFIRMED", confirmation_id=confirmation_id)

    def stop_billing(self, verified_no_future_charges: bool) -> None:
        if not verified_no_future_charges:
            raise CancellationError("future recurring charges not verified stopped")
        self._go("BILLING_STOPPED")

    def send_receipt(self, receipt_ref: str) -> None:
        self._go("RECEIPT_SENT", receipt_ref=receipt_ref)

    def record(self) -> dict[str, Any]:
        self._go("RECORDED")
        return {"subscription_id": self.subscription_id, "history": self.history,
                "save_offers_shown": self.save_offers_shown}
