"""Consent ledger and global suppression list (spec §21, CAN-SPAM, TCPA, CASL, PECR).

The consent ledger is a *data store* (it holds the contact, because CASL
puts the burden of proving consent on the sender). It is subject to data
rights requests. The suppression list holds only salted hashes: keeping a
hash of someone who opted out is how we keep honouring the opt-out after
we have deleted everything else about them.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..home import bau_home

# How long implied consent lasts under CASL s.10(10): 2 years after a purchase or
# contract, 6 months after an inquiry. Express consent lasts until withdrawn.
CASL_IMPLIED_DAYS = {"implied_purchase": 730, "implied_inquiry": 183}

BASES = {
    "express_opt_in",          # clear affirmative act, unbundled (GDPR/PECR/CASL express)
    "double_opt_in",           # express + confirmed address ownership
    "prior_express_written",   # TCPA marketing texts/calls: signed (E-SIGN) written agreement
    "implied_purchase",        # CASL implied (existing business relationship - purchase)
    "implied_inquiry",         # CASL implied (inquiry)
    "soft_opt_in",             # PECR/ePrivacy: existing customer, similar products, opt-out offered
    "existing_relationship",   # US-only: no consent required by CAN-SPAM, opt-out regime
}
EXPRESS = {"express_opt_in", "double_opt_in", "prior_express_written"}


def normalize(contact: str) -> str:
    return contact.strip().lower()


@dataclass
class ConsentRecord:
    consent_id: str
    contact: str
    channel: str              # email | sms | voice
    purpose: str              # marketing | newsletter | product_updates ...
    basis: str
    captured_at: str
    source: str               # form URL / import / point of sale
    consent_text_version: str
    evidence_ref: str         # hash of the form/page snapshot the person saw
    jurisdiction: str
    expires_at: str | None = None
    withdrawn_at: str | None = None
    wireless_authorized: bool = False  # FCC 47 CFR 64.3100 express prior authorization

    def valid_on(self, when: dt.datetime) -> bool:
        if self.withdrawn_at and dt.datetime.fromisoformat(self.withdrawn_at) <= when:
            return False
        if self.expires_at and dt.datetime.fromisoformat(self.expires_at) < when:
            return False
        return dt.datetime.fromisoformat(self.captured_at) <= when


class ConsentLedger:
    def __init__(self, path: Path | None = None):
        self.path = path or (bau_home() / "consent" / "ledger.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _all(self) -> list[ConsentRecord]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text().splitlines():
            if line.strip():
                out.append(ConsentRecord(**json.loads(line)))
        return out

    def _write_all(self, recs: list[ConsentRecord]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(asdict(r), sort_keys=True) + "\n" for r in recs))
        tmp.replace(self.path)

    def record(self, contact: str, channel: str, purpose: str, basis: str, source: str,
               consent_text_version: str, evidence_ref: str, jurisdiction: str,
               captured_at: dt.datetime | None = None, wireless_authorized: bool = False
               ) -> ConsentRecord:
        if basis not in BASES:
            raise ValueError(f"unknown consent basis {basis!r}")
        if not evidence_ref:
            raise ValueError("consent without evidence is not consent (spec §21)")
        captured = captured_at or dt.datetime.now(dt.UTC)
        expires = None
        if basis in CASL_IMPLIED_DAYS:
            expires = (captured + dt.timedelta(days=CASL_IMPLIED_DAYS[basis])).isoformat()
        rec = ConsentRecord(
            consent_id="cns_" + secrets.token_hex(8), contact=normalize(contact),
            channel=channel, purpose=purpose, basis=basis, captured_at=captured.isoformat(),
            source=source, consent_text_version=consent_text_version,
            evidence_ref=evidence_ref, jurisdiction=jurisdiction, expires_at=expires,
            wireless_authorized=wireless_authorized)
        with self.path.open("a") as fh:
            fh.write(json.dumps(asdict(rec), sort_keys=True) + "\n")
        return rec

    def current(self, contact: str, channel: str, purpose: str,
                when: dt.datetime | None = None) -> ConsentRecord | None:
        when = when or dt.datetime.now(dt.UTC)
        c = normalize(contact)
        best = None
        for r in self._all():
            if r.contact == c and r.channel == channel and r.purpose == purpose \
                    and r.valid_on(when):
                if best is None or (r.basis in EXPRESS and best.basis not in EXPRESS):
                    best = r
        return best

    def withdraw(self, contact: str, channel: str | None = None,
                 when: dt.datetime | None = None) -> int:
        """Withdraw consent. channel=None withdraws everything (TCPA: treat revocation broadly)."""
        when = when or dt.datetime.now(dt.UTC)
        c, n = normalize(contact), 0
        recs = self._all()
        for r in recs:
            if r.contact == c and (channel is None or r.channel == channel) and not r.withdrawn_at:
                r.withdrawn_at = when.isoformat()
                n += 1
        self._write_all(recs)
        return n

    def withdraw_where(self, match, when: dt.datetime | None = None) -> int:
        """Withdraw every consent whose contact satisfies ``match`` (used by hashed opt-outs)."""
        when = when or dt.datetime.now(dt.UTC)
        recs, n = self._all(), 0
        for r in recs:
            if match(r.contact) and not r.withdrawn_at:
                r.withdrawn_at = when.isoformat()
                n += 1
        self._write_all(recs)
        return n

    def erase(self, contact: str) -> int:
        """Data-rights deletion. Callers must suppress first so the opt-out survives."""
        c = normalize(contact)
        recs = self._all()
        keep = [r for r in recs if r.contact != c]
        self._write_all(keep)
        return len(recs) - len(keep)


class SuppressionList:
    """Global do-not-contact list across every channel, campaign, and brand."""

    def __init__(self, path: Path | None = None, salt: str = "bau-suppression"):
        self.path = path or (bau_home() / "suppression" / "global.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.salt = salt
        self._cache: dict[str, dict[str, Any]] | None = None

    def key(self, contact: str) -> str:
        return hashlib.sha256(f"{self.salt}:{normalize(contact)}".encode()).hexdigest()

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._cache is None:
            self._cache = {}
            if self.path.exists():
                for line in self.path.read_text().splitlines():
                    if line.strip():
                        rec = json.loads(line)
                        self._cache[rec["key"]] = rec
        return self._cache

    def add(self, contact: str, reason: str, channel: str = "all") -> dict[str, Any]:
        return self.add_key(self.key(contact), reason, channel)

    def add_key(self, key: str, reason: str, channel: str = "all") -> dict[str, Any]:
        rec = {"key": key, "reason": reason, "channel": channel,
               "added_at": dt.datetime.now(dt.UTC).isoformat()}
        with self.path.open("a") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
        self._load()[rec["key"]] = rec
        return rec

    def is_suppressed(self, contact: str, channel: str = "email") -> bool:
        rec = self._load().get(self.key(contact))
        return rec is not None and rec["channel"] in ("all", channel)


class UnsubscribeTokens:
    """Signed, non-guessable unsubscribe tokens for RFC 8058 one-click links.

    The token carries only the salted suppression hash and the list id, so the
    address never appears in a URL; it needs no login, and the HMAC stops
    anyone forging a token to unsubscribe someone else.
    """

    def __init__(self, key: bytes):
        if len(key) < 16:
            raise ValueError("unsubscribe signing key must be at least 16 bytes")
        self.key = key

    def make(self, suppression_key: str, list_id: str) -> str:
        if "." in list_id or "|" in list_id:
            raise ValueError("list_id may not contain '.' or '|'")
        payload = f"{suppression_key}|{list_id}"
        mac = hmac.new(self.key, payload.encode(), hashlib.sha256).hexdigest()[:32]
        return f"{payload}.{mac}"

    def parse(self, token: str) -> tuple[str, str]:
        try:
            payload, mac = token.rsplit(".", 1)
            skey, list_id = payload.split("|", 1)
        except ValueError as e:
            raise ValueError("malformed token") from e
        good = hmac.new(self.key, payload.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(mac, good):
            raise ValueError("invalid token signature")
        return skey, list_id
