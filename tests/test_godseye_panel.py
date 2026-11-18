"""God's Eye on the Jarvis screen: a world map with public layers (earthquakes, aircraft by
named region, satellites), every query recorded with its purpose, cached so public
sources aren't hammered, and never aimed at a person. Written before the code it tests."""

import io
import json
import threading
import urllib.error
import urllib.request

import pytest

from bau.assistant import TOOL_NODE, Assistant, Voice
from bau.audit import AuditLog
from bau.spatial import SpatialRefused
from bau.ui import screen

QUAKES = {"features": [
    {"geometry": {"coordinates": [-122.8, 38.8, 2.1]},
     "properties": {"mag": 2.4, "place": "5 km NW of The Geysers, CA", "time": 1791640000000}},
    {"geometry": {"coordinates": [142.1, 38.3, 30]},
     "properties": {"mag": 5.6, "place": "off the east coast of Honshu, Japan",
                    "time": 1791641000000}},
    {"geometry": {"coordinates": [0, 0, 0]}, "properties": {"mag": None, "place": "?",
                                                           "time": 0}}]}
STATES = {"states": [["abc123", "DAL123 ", "United States", 0, 0, -80.1, 25.8, 10000, False,
                      230, 0, 0, None, 10100, None, False, 0]] * 3}
SATS = [{"OBJECT_NAME": "ISS (ZARYA)", "NORAD_CAT_ID": 25544, "EPOCH": "2026-10-10T00:00:00",
         "INCLINATION": 51.6, "MEAN_MOTION": 15.5}]
FIRES = (b"latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
         b"instrument,confidence,version,bright_ti5,frp,daynight\n"
         b"27.1,-81.2,330.1,0.4,0.4,2026-11-18,1234,N,VIIRS,high,2.0NRT,290.2,1.1,N\n"
         b"38.2,-122.3,310.0,0.4,0.4,2026-11-18,1235,N,VIIRS,nominal,2.0NRT,280.0,0.8,D\n"
         b"51.5,-0.1,300.0,0.4,0.4,2026-11-18,1236,N,VIIRS,low,2.0NRT,270.0,0.2,D\n")
WEATHER = {"current": {"time": "2026-11-18T12:00", "temperature_2m": 9.4,
                       "apparent_temperature": 7.1, "relative_humidity_2m": 81,
                       "precipitation": 0.0, "weather_code": 3, "wind_speed_10m": 3.2,
                       "wind_direction_10m": 240}}
KP = [{"time_tag": "2026-11-18T09:00:00", "Kp": 1.67, "a_running": 6, "station_count": 8},
      {"time_tag": "2026-11-18T12:00:00", "Kp": 5.33, "a_running": 18,
       "station_count": 8}]
TRAFFIC = {"incidents": [{"geometry": {"type": "Point", "coordinates": [4.9, 52.3]},
                          "properties": {"iconCategory": 6, "magnitudeOfDelay": 2,
                                         "delay": 120, "length": 800,
                                         "roadNumbers": ["A10"],
                                         "events": [{"description": "roadworks"}]}}]}


class Opener:
    def __init__(self):
        self.urls = []

    def __call__(self, req, timeout=30):
        url = req.full_url
        self.urls.append(url)
        if "usgs" in url:
            body = json.dumps(QUAKES).encode()
        elif "opensky" in url:
            body = json.dumps(STATES).encode()
        elif "firms" in url:
            body = FIRES
        elif "open-meteo" in url:
            body = json.dumps(WEATHER).encode()
        elif "swpc" in url:
            body = json.dumps(KP).encode()
        elif "tomtom" in url:
            body = json.dumps(TRAFFIC).encode()
        else:
            body = json.dumps(SATS).encode()
        return _Resp(body)


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def asst(tmp_path):
    a = Assistant(tmp_path, None, {}, "human:owner",
                  AuditLog(tmp_path / "audit" / "chain.jsonl", key=b""),
                  clients={"spatial_opener": Opener()})
    return a


def test_earthquakes_layer_is_ready_to_plot_and_recorded_with_its_purpose(asst):
    d = screen.godseye_layer(asst, {"layer": "earthquakes", "window": "all_day"})
    pts = d["points"]
    assert [p["mag"] for p in pts] == [5.6, 2.4]              # biggest first, no blanks
    assert pts[0]["lon"] == 142.1 and pts[0]["lat"] == 38.3 and "Honshu" in pts[0]["label"]
    assert "USGS" in d["licence"] and d["count"] == 2
    ev = [r for r in asst.audit.records() if r["event"] == "godseye.query"]
    assert ev and ev[-1]["data"]["layer"] == "earthquakes" and ev[-1]["data"]["purpose"]


def test_aircraft_only_by_named_region_never_a_spot(asst):
    regions = screen.GODSEYE_REGIONS
    assert "florida" in regions and all(
        (b[2] - b[0]) * (b[3] - b[1]) >= 4 for b in regions.values())  # wide areas only
    d = screen.godseye_layer(asst, {"layer": "aircraft", "region": "florida"})
    assert d["count"] == 3 and d["points"][0]["label"].startswith("DAL123")
    assert "non-commercial" in d["licence"]
    with pytest.raises(ValueError):
        screen.godseye_layer(asst, {"layer": "aircraft", "region": "my neighbour's house"})
    with pytest.raises(ValueError):
        screen.godseye_layer(asst, {"layer": "aircraft", "bbox": [25, -80, 25.1, -79.9]})


def test_satellites_are_listed_without_pretending_to_know_positions(asst):
    d = screen.godseye_layer(asst, {"layer": "satellites", "group": "stations"})
    assert d["points"] == [] and d["list"][0]["name"] == "ISS (ZARYA)"
    assert "positions are not computed" in d["note"]


def test_fires_weather_and_space_weather_work_without_keys(asst):
    d = screen.godseye_layer(asst, {"layer": "fires", "region": "world"})
    assert d["count"] == 3 and d["points"][0]["label"].startswith("fire · high")
    assert "NASA" in d["licence"]
    d = screen.godseye_layer(asst, {"layer": "fires", "region": "florida"})
    assert d["count"] == 1 and d["points"][0]["lat"] == 27.1
    d = screen.godseye_layer(asst, {"layer": "weather", "region": "europe"})
    assert d["count"] == 1 and d["points"][0]["temperature_c"] == 9.4
    assert "overcast" in d["points"][0]["label"] and "centre" in d["note"]
    d = screen.godseye_layer(asst, {"layer": "space_weather"})
    assert d["points"] == [] and d["list"][-1]["kp"] == 5.33 and d["list"][-1]["storm"]
    assert "Kp 5" in d["note"]


def test_traffic_and_ships_say_which_key_they_need(asst, monkeypatch):
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    monkeypatch.delenv("AISSTREAM_API_KEY", raising=False)
    r = screen.godseye_screen(asst, {"layer": "traffic", "region": "europe"})
    assert "TOMTOM_API_KEY" in r["error"]
    r = screen.godseye_screen(asst, {"layer": "ships", "region": "europe"})
    assert "AISSTREAM_API_KEY" in r["error"]
    monkeypatch.setenv("TOMTOM_API_KEY", "test-key")
    d = screen.godseye_layer(asst, {"layer": "traffic", "region": "europe"})
    assert d["count"] == 1 and "roadworks" in d["points"][0]["label"]
    assert "TomTom" in d["licence"]


def test_results_are_cached_so_public_sources_are_not_hammered(asst):
    op = asst.clients["spatial_opener"]
    screen.godseye_layer(asst, {"layer": "earthquakes", "window": "all_day"})
    screen.godseye_layer(asst, {"layer": "earthquakes", "window": "all_day"})
    assert len(op.urls) == 1
    screen.godseye_layer(asst, {"layer": "earthquakes", "window": "all_week"})
    assert len(op.urls) == 2


def test_world_outline_is_shipped_small_and_public_domain():
    w = screen.godseye_world()
    assert len(w["land"]) > 50 and "public domain" in w["credit"]
    assert all(-180 <= x <= 180 for ring in w["land"] for x in ring[0::2])
    from importlib import resources
    assert (resources.files("bau") / "data" / "world-land.json").stat().st_size < 60_000


def test_jarvis_tool_refuses_person_targeting(asst):
    assert asst.tools["world_watch"].kind == "read" and TOOL_NODE["world_watch"] == "godseye"
    out, err = asst._run_tool("world_watch", {"layer": "earthquakes",
                                              "why": "morning briefing on world events"})
    assert not err and out["count"] == 2 and out["strongest"].startswith("M5.6")
    out, err = asst._run_tool("world_watch", {"layer": "aircraft", "region": "florida",
                                              "why": "track my ex wife's flight home"})
    assert err


def test_node_endpoints_and_page(asst, tmp_path):
    from bau.overview import overview
    from bau.ui.jarvis_server import serve
    assert "godseye" in {n["id"] for n in overview(asst)["nodes"]}
    srv, _ = serve(asst, Voice(tmp_path), 0, key="k123")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        def call(path, body=None, key="k123"):
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(base + path, data=data, headers={
                "X-Jarvis-Key": key, "Content-Type": "application/json"})
            with urllib.request.urlopen(req) as r:
                return json.loads(r.read())
        with pytest.raises(urllib.error.HTTPError):
            call("/api/godseye/world", key="nope")
        assert call("/api/godseye/world")["land"]
        r = call("/api/godseye", {"layer": "earthquakes", "window": "all_day"})
        for _ in range(60):                       # a slow source becomes a job, like Scout
            if "job" not in r:
                break
            import time
            time.sleep(.05)
            r = call(f"/api/job/{r['job']}")
        assert r["count"] == 2
        assert call("/api/godseye", {"layer": "aircraft", "region": "nowhere"})["error"]
    finally:
        srv.shutdown()
    from importlib import resources
    page = (resources.files("bau.ui") / "jarvis.html").read_text()
    assert 'n.id === "godseye"' in page and "function renderGodsEye" in page
    assert "/api/godseye/world" in page


def test_spatial_guard_still_refuses_people():
    from bau.spatial import guard
    with pytest.raises(SpatialRefused):
        guard("find where does John Smith live")


def test_a_source_that_says_slow_down_is_left_alone_until_it_said(asst):
    from email.message import Message
    calls = []

    def busy(req, timeout=30):
        calls.append(req.full_url)
        h = Message()
        h["Retry-After"] = "120"
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", h, None)
    asst.clients["spatial_opener"] = busy
    r = screen.godseye_screen(asst, {"layer": "aircraft", "region": "florida"})
    assert "asked BAU to wait" in r["error"] and len(calls) == 1
    r = screen.godseye_screen(asst, {"layer": "aircraft", "region": "europe"})
    assert "asked BAU to wait" in r["error"] and len(calls) == 1      # nothing sent


def test_private_aircraft_are_not_named(asst):
    private = [["a1b2c3", "N4791E  ", "United States", 0, 0, -81.0, 27.0, 244, False, 60, 0, 0,
                None, 250, None, False, 0]]
    asst.clients["spatial_opener"] = lambda req, timeout=30: _Resp(json.dumps(
        {"states": STATES["states"] + private}).encode())
    d = screen.godseye_layer(asst, {"layer": "aircraft", "region": "usa-east"})
    labels = [p["label"] for p in d["points"]]
    assert any(lb.startswith("DAL123") for lb in labels)          # airline flights by number
    assert not any("N4791E" in lb or "a1b2c3" in lb for lb in labels)
    assert any(lb.startswith("private aircraft") for lb in labels)
