"""Sanctions screening (OFAC SDN + comprehensively sanctioned regions).

Load the official SDN list (``sdn.csv`` from ofac.treasury.gov) with
``bau sanctions import``. Screening is a tripwire: HIT blocks, REVIEW goes to a
human, CLEAR proceeds. A list older than 7 days makes every result REVIEW.
"""

from __future__ import annotations

import csv
import datetime as dt
import difflib
import re
import unicodedata
from pathlib import Path
from typing import Any

from .home import bau_home
from .store import YamlStore

# Comprehensive embargoes as of 2026-10 (Syria's program ended 2025-07-01 / 31 CFR 542
# removed 2025-08-26). Region codes follow ISO 3166-2 where they exist. Verify with OFAC.
EMBARGOED = {"CU": "Cuba", "IR": "Iran", "KP": "North Korea", "UA-43": "Crimea",
             "UA-14": "Donetsk (so-called DNR) - covered regions",
             "UA-09": "Luhansk (so-called LNR) - covered regions"}


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return " ".join(sorted(t for t in s.split() if t not in {"the", "of", "and", "llc",
                                                              "ltd", "inc", "co", "sa"}))


class SanctionsList:
    def __init__(self, home: Path | None = None):
        self.path = (home or bau_home()) / "compliance" / "sdn.yaml"

    def import_sdn_csv(self, src: Path, fetched_at: str) -> int:
        names = []
        with src.open(newline="", encoding="latin-1") as fh:
            for row in csv.reader(fh):
                if len(row) > 3 and row[1].strip() and row[1].strip() != "-0-":
                    names.append({"name": row[1].strip(), "type": row[2].strip(),
                                  "program": row[3].strip(), "norm": norm(row[1])})
        YamlStore(self.path).save({"fetched_at": fetched_at, "entries": names})
        return len(names)

    def screen(self, name: str, country: str | None = None, region: str | None = None,
               on: dt.date | None = None) -> dict[str, Any]:
        on = on or dt.date.today()
        data = YamlStore(self.path, {"fetched_at": None, "entries": []}).load()
        res: dict[str, Any] = {"name_screened": bool(name), "matches": []}
        for code in filter(None, [country, region]):
            if code.upper() in EMBARGOED:
                return dict(res, result="HIT",
                            reason=f"comprehensively sanctioned: {EMBARGOED[code.upper()]}")
        if not data.get("fetched_at"):
            return dict(res, result="REVIEW", reason="SDN list not loaded")
        age = (on - dt.date.fromisoformat(str(data["fetched_at"]))).days
        n = norm(name)
        best = []
        for e in data["entries"]:
            r = difflib.SequenceMatcher(None, n, e["norm"]).ratio()
            if r >= 0.8:
                best.append({"sdn_name": e["name"], "program": e["program"],
                             "score": round(r, 3)})
        best.sort(key=lambda x: -x["score"])
        res["matches"] = best[:5]
        if best and best[0]["score"] >= 0.92:
            return dict(res, result="HIT", reason="close SDN name match")
        if best:
            return dict(res, result="REVIEW", reason="possible SDN match - human review")
        if age > 7:
            return dict(res, result="REVIEW", reason=f"SDN list is {age} days old")
        return dict(res, result="CLEAR", reason="no match")
