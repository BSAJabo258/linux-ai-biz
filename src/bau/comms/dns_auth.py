"""Sender-authentication checks: SPF, DKIM, DMARC (mailbox-provider bulk-sender rules).

DNS lookups go through an injectable resolver so the checks are testable
and so a missing resolver yields *missing facts* (INCOMPLETE_FACTS), never
a silent pass.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable

Resolver = Callable[[str], list[str] | None]


def dig_txt(name: str) -> list[str] | None:
    """Return TXT strings for name, [] if none, None if we cannot resolve at all."""
    dig = shutil.which("dig")
    if not dig:
        return None
    try:
        out = subprocess.run([dig, "+short", "+time=3", "+tries=2", "TXT", name],
                             capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    recs = []
    for line in out.stdout.splitlines():
        # dig splits long TXT records into quoted chunks: "abc" "def"
        parts = [p for p in line.strip().split('"') if p.strip()]
        recs.append("".join(parts))
    return recs


def _tags(record: str) -> dict[str, str]:
    out = {}
    for part in record.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip().lower()] = v.strip()
    return out


def check_domain(domain: str, dkim_selectors: list[str], resolver: Resolver = dig_txt
                 ) -> dict[str, object]:
    facts: dict[str, object] = {}
    spf = resolver(domain)
    if spf is not None:
        spf_recs = [r for r in spf if r.lower().startswith("v=spf1")]
        facts["spf_present"] = len(spf_recs) == 1
        facts["spf_single_record"] = len(spf_recs) <= 1  # RFC 7208: >1 record is a permerror
        facts["spf_not_permissive"] = bool(spf_recs) and "+all" not in spf_recs[0].lower()
    dmarc = resolver(f"_dmarc.{domain}")
    if dmarc is not None:
        recs = [r for r in dmarc if r.lower().startswith("v=dmarc1")]
        facts["dmarc_present"] = len(recs) == 1
        if recs:
            t = _tags(recs[0])
            facts["dmarc_policy"] = t.get("p", "").lower()
            facts["dmarc_rua"] = t.get("rua", "").lower().startswith("mailto:")
    if dkim_selectors:
        ok = []
        for sel in dkim_selectors:
            recs = resolver(f"{sel}._domainkey.{domain}")
            if recs is None:
                ok = None
                break
            ok.append(any(_tags(r).get("p") for r in recs))
        if ok is not None:
            facts["dkim_present"] = all(ok)
    return facts
