"""God's Eye: BAU spatial intelligence over public data (spec §59).

Only authorized, public sources: USGS earthquakes, OpenSky aircraft state
vectors, CelesTrak satellite elements, and public webcams from an explicit
allow-list. Queries that target a private person (names, phone numbers,
emails, home addresses, tail numbers tied to individuals) are refused: no
covert surveillance or stalking, ever.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SOURCES = {
    "earthquakes": ("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/"
                    "{window}.geojson", "USGS - public domain"),
    "aircraft": ("https://opensky-network.org/api/states/all?{bbox}",
                 "OpenSky Network - non-commercial terms; commercial use needs a licence"),
    "satellites": ("https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=json",
                   "CelesTrak - public orbital elements"),
}
PERSON_TARGETING = re.compile(
    r"\b(home address|where does .* live|track (him|her|my (ex|wife|husband|partner))|"
    r"follow (him|her)|person named|stalk)\b|[\w.+-]+@[\w-]+\.[\w.]+|"
    r"(?<![\d-])(\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?![\d-])",
    re.IGNORECASE)


class SpatialRefused(PermissionError):
    pass


def _get_json(url: str, opener: Any = None, timeout: int = 30) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "BAU-spatial/0.1"})
    with (opener or urllib.request.urlopen)(req, timeout=timeout) as r:
        return json.loads(r.read())


def guard(purpose: str) -> None:
    if PERSON_TARGETING.search(purpose or ""):
        raise SpatialRefused("query appears to target a private individual - refused")
    if not purpose or len(purpose.strip()) < 8:
        raise SpatialRefused("state the purpose of the query (recorded with the result)")


class GodsEye:
    def __init__(self, opener: Any = None, camera_allowlist: dict[str, str] | None = None):
        self.opener = opener
        self.cameras = camera_allowlist or {}

    def earthquakes(self, purpose: str, window: str = "all_day") -> dict[str, Any]:
        guard(purpose)
        if window not in ("all_hour", "all_day", "all_week", "significant_week",
                          "4.5_day", "2.5_day"):
            raise ValueError("unsupported USGS window")
        url, lic = SOURCES["earthquakes"]
        data = _get_json(url.format(window=window), self.opener)
        return self._wrap("earthquakes", purpose, lic, data.get("features", []))

    def aircraft(self, purpose: str, bbox: tuple[float, float, float, float]) -> dict[str, Any]:
        guard(purpose)
        lamin, lomin, lamax, lomax = bbox
        if (lamax - lamin) * (lomax - lomin) < 0.01:
            raise SpatialRefused("bounding box too small - looks like tracking one location")
        url, lic = SOURCES["aircraft"]
        q = urllib.parse.urlencode({"lamin": lamin, "lomin": lomin, "lamax": lamax,
                                    "lomax": lomax})
        data = _get_json(url.format(bbox=q), self.opener)
        feats = []
        for s in data.get("states") or []:
            if s[5] is None or s[6] is None:
                continue
            feats.append({"type": "Feature",
                          "geometry": {"type": "Point", "coordinates": [s[5], s[6]]},
                          "properties": {"icao24": s[0], "callsign": (s[1] or "").strip(),
                                         "origin_country": s[2], "altitude_m": s[7],
                                         "velocity_ms": s[9]}})
        return self._wrap("aircraft", purpose, lic, feats)

    def satellites(self, purpose: str, group: str = "stations") -> dict[str, Any]:
        guard(purpose)
        if not re.fullmatch(r"[a-z0-9-]{2,30}", group):
            raise ValueError("invalid CelesTrak group")
        url, lic = SOURCES["satellites"]
        data = _get_json(url.format(group=group), self.opener)
        feats = [{"type": "Feature", "geometry": None,
                  "properties": {k: d.get(k) for k in ("OBJECT_NAME", "NORAD_CAT_ID",
                                                       "EPOCH", "INCLINATION",
                                                       "MEAN_MOTION")}} for d in data]
        return self._wrap("satellites", purpose, lic, feats)

    def public_camera(self, purpose: str, name: str) -> dict[str, Any]:
        guard(purpose)
        if name not in self.cameras:
            raise SpatialRefused("camera not on the public-camera allow-list")
        return {"camera": name, "url": self.cameras[name], "purpose": purpose}

    @staticmethod
    def _wrap(kind: str, purpose: str, licence: str, features: list[Any]) -> dict[str, Any]:
        return {"type": "FeatureCollection", "features": features,
                "bau": {"source": kind, "purpose": purpose, "licence": licence,
                        "retrieved_at": dt.datetime.now(dt.UTC).isoformat(),
                        "count": len(features)}}


def create_scene(layers: list[dict[str, Any]], title: str) -> dict[str, Any]:
    feats: list[Any] = []
    licences = set()
    for layer in layers:
        for f in layer["features"]:
            f = dict(f)
            f.setdefault("properties", {})["layer"] = layer["bau"]["source"]
            feats.append(f)
        licences.add(layer["bau"]["licence"])
    return {"type": "FeatureCollection", "features": feats,
            "bau": {"title": title, "licences": sorted(licences),
                    "created_at": dt.datetime.now(dt.UTC).isoformat()}}


def export_scene(scene: dict[str, Any], out: Path) -> Path:
    out.write_text(json.dumps(scene, indent=1))
    return out


# ------------------------------------------------------------------ the sky (timely post ideas)
# The owner's ask (2026-11-10): God's Eye helps the money loop with timely post ideas. The
# sky layer is worked out on this computer (no network): the Moon's phase, the solstices and
# equinoxes, and the major meteor-shower peaks. The creator feed turns a moment into the
# theme of the day's first post. Disasters are deliberately not a theme.
SYNODIC_DAYS = 29.530588853                                  # mean length of a lunar month
NEW_MOON = dt.datetime(2000, 1, 6, 18, 14, tzinfo=dt.UTC)     # a known new moon (Meeus)
# Peaks read 2026-11-10 (space.com "Meteor showers 2026", rmg.co.uk, amsmeteors.org); the
# sources differ by a day, so each counts one day either side.
METEOR_PEAKS = {(1, 3): "Quadrantid", (4, 22): "Lyrid", (5, 6): "Eta Aquariid",
                (8, 12): "Perseid", (10, 21): "Orionid", (11, 17): "Leonid",
                (12, 13): "Geminid"}
# Northern-hemisphere names (the audience the owner targets); dates move by a day year to year.
SEASONS = {(3, 20): ("spring equinox", "the first day of spring, fresh flowers and light layers"),
           (6, 21): ("summer solstice", "the longest day of the year, a golden hour that "
                                         "lasts forever"),
           (9, 22): ("autumn equinox", "the first day of autumn, warm layers and falling leaves"),
           (12, 21): ("winter solstice", "the longest night of the year, candles and cozy "
                                         "knitwear")}


def moon_age(when: dt.datetime) -> float:
    """Days since the last new moon (0 = new, about 14.8 = full)."""
    return ((when - NEW_MOON).total_seconds() / 86400) % SYNODIC_DAYS


def sky_moments(day: dt.date) -> list[dict[str, str]]:
    """Today's sky moments, each with a post theme for a lifestyle creator."""
    out = []
    age = moon_age(dt.datetime(day.year, day.month, day.day, 12, tzinfo=dt.UTC))
    if abs(age - SYNODIC_DAYS / 2) < 1.0:
        out.append({"kind": "moon", "name": "full moon",
                    "theme": "a full moon night, wrapped in a blanket on the balcony"})
    elif age < 1.0 or age > SYNODIC_DAYS - 1.0:
        out.append({"kind": "moon", "name": "new moon",
                    "theme": "a dark-sky night, stargazing far from the city lights"})
    for (m, d), name in METEOR_PEAKS.items():
        if abs((day - dt.date(day.year, m, d)).days) <= 1:
            out.append({"kind": "meteors", "name": f"{name} meteor shower",
                        "theme": f"watching the {name} meteor shower under the night sky"})
    for (m, d), (name, theme) in SEASONS.items():
        if abs((day - dt.date(day.year, m, d)).days) <= 1:
            out.append({"kind": "season", "name": name, "theme": theme})
    return out
