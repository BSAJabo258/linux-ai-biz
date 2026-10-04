"""Marketing text messages (TCPA, FCC revocation rule, state mini-TCPAs).

Texts carry the largest private-litigation exposure of any channel
(statutory damages per message), so the gate is strict: prior express
written consent, recipient-local quiet hours, DNC scrub, STOP handling.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .. import jurisdiction
from ..audit import ref
from ..decision import Decision
from ..policy import PolicyEngine
from .consent import ConsentLedger, SuppressionList

# FCC 2024 order (in effect 2025-04-11): these words, alone or in a short reply,
# revoke consent; any other reasonable expression of revocation also counts.
STOP_WORDS = {"stop", "quit", "end", "revoke", "opt out", "optout", "cancel", "unsubscribe",
              "stopall"}
_REVOKE_RX = re.compile(r"\b(stop|don'?t (text|message|contact) me|remove me|leave me alone|"
                        r"opt[- ]?out|unsubscribe)\b", re.IGNORECASE)


def is_revocation(reply: str) -> bool:
    t = reply.strip().lower().strip(".! ")
    return t in STOP_WORDS or bool(_REVOKE_RX.search(reply))


def handle_inbound(reply: str, number: str, ledger: ConsentLedger,
                   suppression: SuppressionList) -> bool:
    """Process a reply. A revocation is honoured across every channel and purpose,
    because the FCC's one-revocation-covers-all waiver expired in 2026."""
    if not is_revocation(reply):
        return False
    suppression.add(number, reason="sms_revocation", channel="all")
    ledger.withdraw(number, channel=None)
    return True


def local_hour(tz_name: str | None, when: dt.datetime) -> int | None:
    if not tz_name:
        return None
    try:
        return when.astimezone(ZoneInfo(tz_name)).hour
    except ZoneInfoNotFoundError:
        return None


def preflight(msg: dict[str, Any], rcpt: dict[str, Any], engine: PolicyEngine,
              ledger: ConsentLedger, suppression: SuppressionList,
              when: dt.datetime | None = None) -> tuple[str, Decision]:
    when = when or dt.datetime.now(dt.UTC)
    juris, assumed = jurisdiction.resolve(rcpt.get("country"), rcpt.get("region"))
    consent = ledger.current(rcpt["number"], "sms", msg.get("purpose", "marketing"), when)
    body = msg.get("body", "")
    facts = {
        "jurisdictions": juris,
        "message": {
            "category": msg.get("category"),
            "sender_identified": bool(msg.get("brand")) and msg.get("brand", "") in body,
            "opt_out_instructions": bool(re.search(r"\bstop\b", body, re.IGNORECASE)),
            "uses_autodialer_or_ai_voice": msg.get("ai_voice", False),
        },
        "recipient": {
            "jurisdiction_assumed": assumed,
            "suppressed": suppression.is_suppressed(rcpt["number"], "sms"),
            "consent_basis": consent.basis if consent else "none",
            "local_hour": local_hour(rcpt.get("timezone"), when),
            "dnc_checked": rcpt.get("dnc_checked"),
            "on_dnc": rcpt.get("on_dnc"),
            "messages_last_24h": rcpt.get("messages_last_24h"),
        },
    }
    return ref(rcpt["number"]), engine.evaluate("sms", facts, on=when.date())
