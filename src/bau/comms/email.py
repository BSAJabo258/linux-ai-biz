"""Commercial email preflight: the ordered gate every send must pass.

ORDER (stages match the policy file; a later stage never runs "instead of"
an earlier one - every stage must pass before the SEND stage):

  10 CLASSIFY        commercial / transactional / mixed (CAN-SPAM primary purpose)
  20 LIST SOURCE     no harvested, dictionary-generated, purchased or rented lists
  30 JURISDICTION    per recipient; unknown location -> strictest union
  40 CONSENT         basis valid for that jurisdiction (CASL / PECR / GDPR / US)
  50 SUPPRESSION     global do-not-contact list, FCC wireless-domain list
  60 IDENTITY        From/Reply-To honest; SPF + DKIM + DMARC, aligned
  70 SUBJECT         not deceptive
  80 CONTENT         identified as an ad; claims substantiated; AI/synthetic disclosure
  90 POSTAL ADDRESS  valid physical postal address
 100 UNSUBSCRIBE     visible link + RFC 8058 one-click headers, no login, no fee, >=30 days
 110 REPUTATION      complaint rate under thresholds
 120 SEND + EVIDENCE only the recipients whose decision may proceed; evidence package written
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import jurisdiction
from ..audit import ref
from ..claims import SUBJECT_DECEPTION, ClaimsRegistry, scan, unsubstantiated
from ..decision import Decision
from ..policy import PolicyEngine
from .consent import EXPRESS, ConsentLedger, SuppressionList

ACCEPTABLE_LIST_SOURCES = {"own_opt_in", "customer", "event_signup", "import_with_proof"}


class WirelessDomains:
    """FCC CAN-SPAM wireless domain list (47 CFR 64.3100).

    File format: first line ``# fetched_at: YYYY-MM-DD`` then one domain per line.
    Senders must not email listed domains without express prior authorization.
    """

    def __init__(self, path: Path | None):
        self.domains: set[str] = set()
        self.fetched_at: dt.date | None = None
        if path and path.exists():
            for line in path.read_text().splitlines():
                line = line.strip()
                if line.startswith("# fetched_at:"):
                    self.fetched_at = dt.date.fromisoformat(line.split(":", 1)[1].strip())
                elif line and not line.startswith("#"):
                    self.domains.add(line.lower())

    def age_days(self, on: dt.date) -> int | None:
        return None if self.fetched_at is None else (on - self.fetched_at).days

    def listed(self, address: str) -> bool:
        domain = address.rsplit("@", 1)[-1].lower()
        return any(domain == d or domain.endswith("." + d) for d in self.domains)


def _domain(addr: str | None) -> str:
    return (addr or "").rsplit("@", 1)[-1].strip(" >").lower()


def message_facts(msg: dict[str, Any], sender: dict[str, Any],
                  claims_registry: ClaimsRegistry | None, on: dt.date) -> dict[str, Any]:
    body = (msg.get("body_text") or "") + "\n" + (msg.get("body_html") or "")
    headers = {k.lower(): v for k, v in (msg.get("headers") or {}).items()}
    lu = headers.get("list-unsubscribe", "")
    owned = {d.lower() for d in sender.get("owned_domains", [])}
    unsub_url = msg.get("unsubscribe_url")
    addr = msg.get("physical_address")
    return {
        "message": {
            "category": msg.get("category"),
            "list_source": msg.get("list_source"),
            "list_source_ok": msg.get("list_source") in ACCEPTABLE_LIST_SOURCES
            if msg.get("list_source") else None,
            "from_domain_owned": _domain(msg.get("from_address")) in owned if owned else None,
            "reply_to_owned": (_domain(msg.get("reply_to") or msg.get("from_address")) in owned)
            if owned else None,
            "from_name_present": bool((msg.get("from_name") or "").strip()),
            "subject_flags": [h["claim_type"] for h in scan(msg.get("subject", ""),
                                                              SUBJECT_DECEPTION)],
            "ad_identified": msg.get("ad_identified"),
            "physical_address_present": bool(addr) and addr in body,
            "unsubscribe_link_present": bool(unsub_url) and unsub_url in body,
            "list_unsubscribe_https": "<https://" in lu,
            "list_unsubscribe_post": headers.get("list-unsubscribe-post", "").replace(" ", "")
            == "List-Unsubscribe=One-Click",
            "unsubscribe_requires_login": sender.get("unsubscribe_requires_login"),
            "unsubscribe_fee": sender.get("unsubscribe_fee"),
            "unsubscribe_window_days": sender.get("unsubscribe_window_days"),
            "unsubscribe_processing_days": sender.get("unsubscribe_processing_days"),
            "sexually_explicit": msg.get("sexually_explicit"),
            "unsubstantiated_claims": [h["claim_type"] for h in unsubstantiated(
                (msg.get("subject") or "") + "\n" + body, claims_registry, on)],
            "contains_testimonial": msg.get("contains_testimonial", False),
            "testimonials_verified": msg.get("testimonials_verified"),
            "material_connection_disclosed": msg.get("material_connection_disclosed"),
            "synthetic_performer": msg.get("synthetic_performer", False),
            "synthetic_performer_disclosed": msg.get("synthetic_performer_disclosed"),
        },
        "sender": {k: sender.get(k) for k in (
            "spf_present", "spf_single_record", "spf_not_permissive", "dkim_present",
            "dmarc_present", "dmarc_policy", "dmarc_rua", "dmarc_aligned", "tls",
            "complaint_rate", "ptr_ok")},
    }


def recipient_facts(rcpt: dict[str, Any], msg: dict[str, Any], ledger: ConsentLedger,
                    suppression: SuppressionList, wireless: WirelessDomains,
                    when: dt.datetime) -> dict[str, Any]:
    addr = rcpt["address"]
    juris, assumed = jurisdiction.resolve(rcpt.get("country"), rcpt.get("region"))
    consent = ledger.current(addr, "email", msg.get("purpose", "marketing"), when)
    return {
        "jurisdictions": juris,
        "recipient": {
            "jurisdiction_assumed": assumed,
            "suppressed": suppression.is_suppressed(addr, "email"),
            "consent_basis": consent.basis if consent else "none",
            "consent_express": bool(consent and consent.basis in EXPRESS),
            "known_minor": rcpt.get("known_minor", False),
            "wireless_domain": wireless.listed(addr),
            "wireless_authorized": bool(consent and consent.wireless_authorized),
        },
        "wireless_list": {"age_days": wireless.age_days(when.date())},
    }


@dataclass
class CampaignReport:
    campaign_id: str
    message_decision: Decision
    recipients: list[dict[str, Any]] = field(default_factory=list)

    @property
    def sendable(self) -> list[str]:
        return [r["ref"] for r in self.recipients if r["may_proceed"]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "message": self.message_decision.to_dict(),
            "message_may_proceed": self.message_decision.may_proceed(),
            "recipients_total": len(self.recipients),
            "recipients_sendable": len(self.sendable),
            "recipients": self.recipients,
        }


def preflight(msg: dict[str, Any], recipients: list[dict[str, Any]], sender: dict[str, Any],
              engine: PolicyEngine, ledger: ConsentLedger, suppression: SuppressionList,
              wireless: WirelessDomains, claims_registry: ClaimsRegistry | None = None,
              when: dt.datetime | None = None, approved: bool = False) -> CampaignReport:
    when = when or dt.datetime.now(dt.UTC)
    on = when.date()
    base = message_facts(msg, sender, claims_registry, on)
    per_rcpt = []
    all_j: list[str] = []
    for r in recipients:
        rf = recipient_facts(r, msg, ledger, suppression, wireless, when)
        all_j = jurisdiction.merge(all_j, rf["jurisdictions"])
        per_rcpt.append((r, rf))
    msg_facts = dict(base, jurisdictions=all_j or None)
    mdec = engine.evaluate("email", msg_facts, scope="message", on=on)
    report = CampaignReport(campaign_id=msg.get("campaign_id", "unknown"), message_decision=mdec)
    for r, rf in per_rcpt:
        facts = dict(base, **rf)
        d = engine.evaluate("email", facts, scope="recipient", on=on)
        report.recipients.append({
            "ref": ref(r["address"]),
            "jurisdictions": rf["jurisdictions"],
            "status": d.status.value,
            "may_proceed": mdec.may_proceed(approved) and d.may_proceed(approved),
            "blocking": [f.to_dict() for f in d.blocking()],
            "resolved": d.resolved,
        })
    return report


def unsubscribe_headers(unsub_https_url: str, mailto: str | None = None) -> dict[str, str]:
    """RFC 2369 + RFC 8058 headers. The POST target must work without login or cookies."""
    if not unsub_https_url.startswith("https://"):
        raise ValueError("one-click unsubscribe URL must be https")
    targets = [f"<{unsub_https_url}>"]
    if mailto:
        targets.append(f"<mailto:{mailto}>")
    return {"List-Unsubscribe": ", ".join(targets),
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
