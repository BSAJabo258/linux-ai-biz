"""God's Eye in the money loop and the briefing (the owner's ask, 2026-11-10): posts wait for
the audience's evening, hold on the day of a major disaster, and the briefing carries the sky,
big earthquakes and the brand-safety state. Fake USGS feed only."""

import datetime as dt
import json

from bau import spatial as S


class Resp:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        return self.body


def feed(*mags):
    return json.dumps({"features": [{"properties": {"mag": m, "place": f"place {m}"}}
                                    for m in mags]}).encode()


def test_only_big_quakes_count_and_a_major_one_holds_the_posts(monkeypatch):
    monkeypatch.undo()                                    # the real lookup, with a fake feed
    qs = S.significant_quakes(opener=lambda req, timeout=0: Resp(feed(4.6, 6.3, 7.4, 5.9)))
    assert [q["mag"] for q in qs] == [7.4, 6.3]
    assert S.brand_pause(qs) == "M7.4 earthquake, place 7.4"
    assert S.brand_pause([{"mag": 6.8, "place": "x"}]) is None

    def down(req, timeout=0):
        raise OSError("offline")
    assert S.significant_quakes(opener=down) is None and S.brand_pause(None) is None


def test_posts_go_out_in_the_audiences_evening():
    ny_evening = dt.datetime(2026, 11, 10, 0, 30, tzinfo=dt.UTC)   # 19:30 in New York
    ny_morning = dt.datetime(2026, 11, 10, 14, 0, tzinfo=dt.UTC)   # 09:00 NY, 14:00 London
    assert S.is_evening(ny_evening) and not S.is_evening(ny_morning)
    assert S.is_evening(ny_morning, ["Asia/Tokyo"]) is False
    assert S.is_evening(dt.datetime(2026, 11, 10, 18, 30, tzinfo=dt.UTC), ["Europe/London"])


def test_autopost_waits_for_the_evening_and_holds_on_a_disaster(tmp_path, monkeypatch):
    from test_fanvue import FakeFanvue, client, picture

    from bau import fanvue as F
    F.set_autopost(tmp_path, True, "human:owner", "subscribers", 2)
    F.Queue(tmp_path).add(picture(tmp_path), "Evening in", 1, "human:owner")
    monkeypatch.setattr(S, "posting_time_ok", lambda home, now: False)
    assert F.autopost_tick(tmp_path, client(tmp_path, FakeFanvue()))["autopost"] == \
        "waiting for the audience's evening"
    monkeypatch.setattr(S, "posting_time_ok", lambda home, now: True)
    monkeypatch.setattr(S, "significant_quakes", lambda *a, **k: [{"mag": 7.6, "place": "Chile"}])
    out = F.autopost_tick(tmp_path, client(tmp_path, FakeFanvue()))
    assert out["autopost"] == "held today for brand safety: M7.6 earthquake, Chile"
    assert F.Queue(tmp_path).pending()                     # still queued, nothing lost


def test_the_briefing_carries_gods_eye(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "significant_quakes", lambda *a, **k: [{"mag": 6.4, "place": "Japan"}])
    w = S.world_now(tmp_path, dt.date(2026, 8, 12))
    assert w == {"tonight_sky": ["new moon", "Perseid meteor shower"],
                 "big_earthquakes_24h": ["M6.4 Japan"], "posting_paused_for_brand_safety": None}
    rows = (tmp_path / "audit" / "chain.jsonl").read_text()
    assert "godseye.query" in rows and "brand safety" in rows           # audited with purpose
