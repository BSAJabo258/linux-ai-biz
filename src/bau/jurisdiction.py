"""Jurisdiction resolution (spec §116-117).

Codes are ISO 3166: ``CA`` is Canada, ``US-CA`` is California. When a
person's location is unknown we never assume the most permissive place:
we return every jurisdiction BAU operates rules for, so the strictest
applicable requirement wins.
"""

from __future__ import annotations

EU_MEMBERS = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE",
    "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
}
# EEA states outside the EU apply GDPR/ePrivacy-equivalent rules.
EEA_EXTRA = {"IS", "LI", "NO"}

# Used when location is unknown: the union of everything we have rules for.
STRICTEST_UNION = ["US", "CA", "EU", "GB", "AU"]


def resolve(country: str | None, region: str | None = None) -> tuple[list[str], bool]:
    """Return (jurisdictions, assumed). ``assumed`` is True when location was unknown."""
    if not country:
        return list(STRICTEST_UNION), True
    c = country.strip().upper()
    if c == "UK":
        c = "GB"
    out = [c]
    if region:
        r = region.strip().upper()
        out.append(r if "-" in r else f"{c}-{r}")
    if c in EU_MEMBERS or c in EEA_EXTRA:
        out.append("EU")
    return out, False


def merge(*sets: list[str]) -> list[str]:
    seen: list[str] = []
    for s in sets:
        for j in s:
            if j not in seen:
                seen.append(j)
    return seen
