"""God's Eye: BAU spatial intelligence over public data (spec §59).

Only authorized, public sources: USGS earthquakes, OpenSky aircraft state
vectors, CelesTrak satellite elements, NASA FIRMS fire detections, Open-Meteo
weather, NOAA space weather, TomTom traffic and AISStream ship positions (the
last two need free API keys), and public webcams from an explicit allow-list.
Queries that target a private person (names, phone numbers, emails, home
addresses, tail numbers tied to individuals) are refused: no covert
surveillance or stalking, ever.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# Wide named regions only: never a box drawn around one home, street or person.
WIDE_REGIONS = {      # (lat min, lon min, lat max, lon max)
    "usa-east": (24.0, -90.0, 47.0, -66.0), "usa-west": (31.0, -125.0, 49.0, -102.0),
    "florida": (24.5, -87.6, 31.0, -80.0), "new-york-area": (39.5, -75.5, 42.0, -71.5),
    "caribbean": (10.0, -90.0, 27.0, -59.0), "uk-ireland": (49.5, -11.0, 59.0, 2.0),
    "europe": (35.0, -10.0, 60.0, 30.0), "japan": (30.0, 129.0, 46.0, 146.0),
}

FIRMS_GLOBAL = ("https://firms.modaps.eosdis.nasa.gov/data/active_fire/"
                "noaa-20-viirs-c2/csv/J1_VIIRS_C2_Global_24h.csv")
FIRMS_AREA = ("https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/"
              "VIIRS_SNPP_NRT/{bbox}/1")
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
SWPC_KP = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
TOMTOM_INCIDENTS = "https://api.tomtom.com/traffic/services/5/incidentDetails"
AISSTREAM = "wss://stream.aisstream.io/v0/stream"

SOURCES = {
    "earthquakes": ("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/"
                    "{window}.geojson", "USGS - public domain"),
    "aircraft": ("https://opensky-network.org/api/states/all?{bbox}",
                 "OpenSky Network - non-commercial terms; commercial use needs a licence"),
    "satellites": ("https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=json",
                   "CelesTrak - public orbital elements"),
    "fires": (FIRMS_GLOBAL, "NASA FIRMS near-real-time fire detections - public data, "
              "attribution requested; not for safety-critical use"),
    "weather": (OPEN_METEO, "Open-Meteo - free for non-commercial use, data CC BY 4.0"),
    "space_weather": (SWPC_KP, "NOAA Space Weather Prediction Center - US Government "
                      "public domain"),
    "traffic": (TOMTOM_INCIDENTS, "TomTom Traffic - needs a free API key and TomTom terms"),
    "ships": (AISSTREAM, "AISStream.io public AIS feed - needs a free API key and AIS terms"),
}
PERSON_TARGETING = re.compile(
    r"\b(home address|where does .* live|track (him|her|my (ex|wife|husband|partner))|"
    r"follow (him|her)|person named|stalk)\b|[\w.+-]+@[\w-]+\.[\w.]+|"
    r"(?<![\d-])(\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?![\d-])",
    re.IGNORECASE)


class SpatialRefused(PermissionError):
    pass


class SpatialUnavailable(RuntimeError):
    """A public source exists but this computer has no key/library for it yet."""


def _get_json(url: str, opener: Any = None, timeout: int = 30) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "BAU-spatial/0.1"})
    with (opener or urllib.request.urlopen)(req, timeout=timeout) as r:
        return json.loads(r.read())


def _get_text(url: str, opener: Any = None, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "BAU-spatial/0.1"})
    with (opener or urllib.request.urlopen)(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _wide(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    lamin, lomin, lamax, lomax = bbox
    if (lamax - lamin) * (lomax - lomin) < 0.01:
        raise SpatialRefused("bounding box too small - looks like tracking one location")
    return bbox


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
        lamin, lomin, lamax, lomax = _wide(bbox)
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

    def fires(self, purpose: str, bbox: tuple[float, float, float, float] | None = None
              ) -> dict[str, Any]:
        """Active fire detections from NASA FIRMS. The global 24-hour CSV needs no key;
        an area query uses FIRMS_MAP_KEY when present (less data, kinder to the service)."""
        guard(purpose)
        if bbox is not None:
            bbox = _wide(bbox)
        key = os.environ.get("FIRMS_MAP_KEY", "").strip()
        url, lic = SOURCES["fires"]
        if bbox is not None and key:
            w, s, e, n = bbox[1], bbox[0], bbox[3], bbox[2]
            url = FIRMS_AREA.format(key=urllib.parse.quote(key, safe=""),
                                    bbox=f"{w},{s},{e},{n}")
        text = _get_text(url, self.opener)
        feats = []
        for row in csv.DictReader(io.StringIO(text)):
            try:
                lat, lon = float(row.get("latitude", "")), float(row.get("longitude", ""))
            except (TypeError, ValueError):
                continue
            if bbox and not (bbox[0] <= lat <= bbox[2] and bbox[1] <= lon <= bbox[3]):
                continue
            conf = str(row.get("confidence", "")).strip().lower()
            feats.append({"type": "Feature",
                          "geometry": {"type": "Point", "coordinates": [lon, lat]},
                          "properties": {"brightness": row.get("bright_ti4"),
                                         "frp": row.get("frp"),
                                         "confidence": {"l": "low", "n": "nominal",
                                                        "h": "high"}.get(conf, conf),
                                         "acq_date": row.get("acq_date"),
                                         "acq_time": row.get("acq_time"),
                                         "daynight": row.get("daynight"),
                                         "satellite": row.get("satellite")}})
            if len(feats) >= 50_000:
                break
        return self._wrap("fires", purpose, lic, feats)

    def weather(self, purpose: str, bbox: tuple[float, float, float, float]) -> dict[str, Any]:
        """Current conditions at the centre of a wide named region (Open-Meteo, no key)."""
        guard(purpose)
        lamin, lomin, lamax, lomax = _wide(bbox)
        lat, lon = (lamin + lamax) / 2, (lomin + lomax) / 2
        q = urllib.parse.urlencode({
            "latitude": f"{lat:.3f}", "longitude": f"{lon:.3f}", "timezone": "UTC",
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                       "precipitation,weather_code,wind_speed_10m,wind_direction_10m"})
        data = _get_json(f"{SOURCES['weather'][0]}?{q}", self.opener)
        cur = data.get("current") or {}
        props = {"region": None, "latitude": lat, "longitude": lon,
                 "time": cur.get("time"), "temperature_c": cur.get("temperature_2m"),
                 "feels_like_c": cur.get("apparent_temperature"),
                 "humidity_pct": cur.get("relative_humidity_2m"),
                 "precipitation_mm": cur.get("precipitation"),
                 "weather_code": cur.get("weather_code"),
                 "wind_ms": cur.get("wind_speed_10m"),
                 "wind_direction_deg": cur.get("wind_direction_10m")}
        feat = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": props}
        return self._wrap("weather", purpose, SOURCES["weather"][1], [feat])

    def space_weather(self, purpose: str) -> dict[str, Any]:
        """Latest planetary K-index readings from NOAA SWPC (no key)."""
        guard(purpose)
        data = _get_json(SOURCES["space_weather"][0], self.opener)
        rows = data if isinstance(data, list) else []
        feats = []
        for row in rows[-24:]:
            if not isinstance(row, dict):
                continue
            try:
                kp = float(row.get("Kp"))
            except (TypeError, ValueError):
                continue
            feats.append({"type": "Feature", "geometry": None,
                          "properties": {"time_tag": row.get("time_tag"), "kp": kp,
                                         "storm": kp >= 5, "a_running": row.get("a_running"),
                                         "station_count": row.get("station_count")}})
        return self._wrap("space_weather", purpose, SOURCES["space_weather"][1], feats)

    def traffic(self, purpose: str, bbox: tuple[float, float, float, float],
                api_key: str | None = None) -> dict[str, Any]:
        """Traffic incidents in a wide region (TomTom; TOMTOM_API_KEY or api_key)."""
        guard(purpose)
        lamin, lomin, lamax, lomax = _wide(bbox)
        key = (api_key or os.environ.get("TOMTOM_API_KEY", "")).strip()
        if not key:
            raise SpatialUnavailable("traffic needs a free TomTom key: set TOMTOM_API_KEY")
        q = urllib.parse.urlencode({
            "key": key, "bbox": f"{lomin},{lamin},{lomax},{lamax}", "language": "en-GB",
            "fields": "{incidents{type,geometry{type,coordinates},properties{id,"
                      "iconCategory,magnitudeOfDelay,events{description,code},"
                      "from,to,length,delay,roadNumbers}}"})
        data = _get_json(f"{SOURCES['traffic'][0]}?{q}", self.opener)
        feats = []
        for inc in (data.get("incidents") or []) if isinstance(data, dict) else []:
            props = inc.get("properties") or {}
            pt = _point(inc.get("geometry") or {})
            if pt is None:
                continue
            events = props.get("events") or []
            label = next((e.get("description") for e in events if e.get("description")), "")
            feats.append({"type": "Feature",
                          "geometry": {"type": "Point", "coordinates": list(pt)},
                          "properties": {"label": str(label)[:160],
                                         "category": props.get("iconCategory"),
                                         "delay_s": props.get("delay"),
                                         "length_m": props.get("length"),
                                         "roads": props.get("roadNumbers") or []}})
        return self._wrap("traffic", purpose, SOURCES["traffic"][1], feats[:400])

    def ships(self, purpose: str, bbox: tuple[float, float, float, float],
              api_key: str | None = None, seconds: float = 8.0) -> dict[str, Any]:
        """Live AIS positions in a wide region (AISStream; AISSTREAM_API_KEY or api_key).

        Vessel names are deliberately not returned: an MMSI can point to a private owner,
        so the map shows the public position and speed only.
        """
        guard(purpose)
        lamin, lomin, lamax, lomax = _wide(bbox)
        key = (api_key or os.environ.get("AISSTREAM_API_KEY", "")).strip()
        if not key:
            raise SpatialUnavailable("ships need a free AISStream key: set AISSTREAM_API_KEY")
        try:
            import websocket
        except ImportError as e:
            raise SpatialUnavailable("ships need the optional websocket-client package") from e
        found: dict[str, dict[str, Any]] = {}
        ws = websocket.create_connection(SOURCES["ships"][0], timeout=10)
        try:
            ws.send(json.dumps({"APIKey": key,
                                "BoundingBoxes": [[[lamin, lomin], [lamax, lomax]]],
                                "FilterMessageTypes": ["PositionReport"]}))
            end = time.monotonic() + max(2.0, min(seconds, 20.0))
            while time.monotonic() < end:
                raw = ws.recv()
                if not raw:
                    break
                msg = json.loads(raw)
                meta = msg.get("MetaData") or {}
                body = msg.get("Message", {}).get("PositionReport") or {}
                try:
                    lat, lon = float(meta["latitude"]), float(meta["longitude"])
                except (KeyError, TypeError, ValueError):
                    continue
                if not (lamin <= lat <= lamax and lomin <= lon <= lomax):
                    continue
                mmsi = str(meta.get("MMSI") or body.get("UserID") or "")
                if not mmsi:
                    continue
                found[mmsi] = {"type": "Feature",
                               "geometry": {"type": "Point", "coordinates": [lon, lat]},
                               "properties": {"mmsi": mmsi,
                                              "speed_knots": body.get("Sog"),
                                              "course_deg": body.get("Cog"),
                                              "heading_deg": body.get("TrueHeading"),
                                              "status": body.get("NavigationalStatus")}}
        finally:
            try:
                ws.close()
            except Exception:  # noqa: BLE001 - a closed socket is not an error here
                pass
        return self._wrap("ships", purpose, SOURCES["ships"][1], list(found.values()))

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


def _point(geometry: dict[str, Any]) -> tuple[float, float] | None:
    """A point or the centre of a line/polygon, for plotting an incident on the world map."""
    coords = geometry.get("coordinates")
    flat: list[tuple[float, float]] = []

    def walk(node: Any) -> None:
        if (isinstance(node, (list, tuple)) and len(node) >= 2
                and isinstance(node[0], (int, float)) and isinstance(node[1], (int, float))):
            flat.append((float(node[0]), float(node[1])))
        elif isinstance(node, (list, tuple)):
            for child in node:
                walk(child)

    walk(coords)
    if not flat:
        return None
    return (sum(p[0] for p in flat) / len(flat), sum(p[1] for p in flat) / len(flat))


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


# ------------------------------------------------------------------ God's Eye for the business
# The owner's ask (2026-11-10): God's Eye in the money loop and every other field. Pure checks
# first (tested directly); the *_now wrappers do the live lookups and fail open (offline means
# no pause, never a stuck business).
MAJOR_MAG = 7.0              # a disaster big enough that a sexy post beside it draws backlash
SIGNIFICANT_MAG = 6.0        # worth a line in the owner's briefing
# The audience's evening, 18:00 to 23:00 local, in the regions the posts are for. US and UK
# by default; the creator profile can list its own `posting_zones`.
POSTING_ZONES = ("America/New_York", "America/Chicago", "America/Los_Angeles", "Europe/London")
EVENING = (18, 23)
BUSINESS_PURPOSE = "BAU business world watch: brand safety and the owner's briefing"


def significant_quakes(opener: Any = None, timeout: int = 6) -> list[dict[str, Any]] | None:
    """M6+ earthquakes of the last 24 hours (USGS, public domain), strongest first; None when
    the feed cannot be reached."""
    url, _ = SOURCES["earthquakes"]
    try:
        data = _get_json(url.format(window="4.5_day"), opener, timeout)
    except Exception:  # noqa: BLE001 - offline, slow or odd: no data, never an error
        return None
    out = []
    for f in data.get("features", []) if isinstance(data, dict) else []:
        p = f.get("properties") or {}
        mag = p.get("mag")
        if isinstance(mag, (int, float)) and mag >= SIGNIFICANT_MAG:
            out.append({"mag": float(mag), "place": str(p.get("place") or "")[:120]})
    return sorted(out, key=lambda q: -q["mag"])


def brand_pause(quakes: list[dict[str, Any]] | None) -> str | None:
    """The reason to hold today's posts, or None."""
    major = [q for q in quakes or [] if q["mag"] >= MAJOR_MAG]
    return f"M{major[0]['mag']:.1f} earthquake, {major[0]['place']}" if major else None


def is_evening(now: dt.datetime, zones: tuple[str, ...] | list[str] = POSTING_ZONES) -> bool:
    from zoneinfo import ZoneInfo
    return any(EVENING[0] <= now.astimezone(ZoneInfo(z)).hour < EVENING[1] for z in zones)


def _audit(home: Path, actor: str, layer: str) -> None:
    from .audit import AuditLog
    AuditLog(home / "audit" / "chain.jsonl").append(
        "godseye.query", actor, {"layer": layer, "purpose": BUSINESS_PURPOSE})


def brand_pause_now(home: Path, actor: str = "autopost") -> str | None:
    _audit(home, actor, "earthquakes")
    return brand_pause(significant_quakes())


def posting_time_ok(home: Path, now: dt.datetime) -> bool:
    zones = POSTING_ZONES
    try:
        import yaml
        found = sorted((home / "creators").glob("*.yaml"))
        prof = yaml.safe_load(found[0].read_text()) if found else {}
        zones = tuple(prof.get("posting_zones") or POSTING_ZONES)
    except (OSError, ValueError, AttributeError):
        pass
    return is_evening(now, zones)


def world_now(home: Path, today: dt.date | None = None) -> dict[str, Any]:
    """God's Eye for the owner's briefing: tonight's sky, big earthquakes, brand safety."""
    today = today or dt.datetime.now(dt.UTC).date()
    _audit(home, "jarvis", "earthquakes")
    quakes = significant_quakes()
    return {"tonight_sky": [m["name"] for m in sky_moments(today)],
            "big_earthquakes_24h": None if quakes is None else
            [f"M{q['mag']:.1f} {q['place']}" for q in quakes[:3]],
            "posting_paused_for_brand_safety": brand_pause(quakes)}
