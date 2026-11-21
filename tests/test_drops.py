"""Weekly drops (src/bau/drops.py): a locked message to her subscribers with a free preview,
and the xxx set to her VIPs, each on a card; only the owner's Accept sends it, once. Fake
Fanvue only: no network, no keys."""

import datetime as dt
import json

import pytest

from bau import drops as D
from bau import fanvue as F
from tests.test_fan_chat import accepted_picture
from tests.test_fan_chat import home as fan_home  # noqa: F401 - the same creator home


class FakeFanvue:
    def __init__(self, fail=False):
        self.sent, self.uploads, self.fail = [], [], fail

    def upload_image(self, path):
        self.uploads.append(path.name)
        return f"media-{path.name}"

    def mass_message(self, smart_list, text, media, preview, price, key):
        if self.fail:
            raise F.FanvueError("Fanvue POST /v1/chats/mass-messages: HTTP 500")
        self.sent.append({"list": smart_list, "text": text, "media": media,
                          "preview": preview, "price": price, "key": key})
        return {"uuid": "mm-1", "recipientCount": 7, "status": "SENT"}


@pytest.fixture
def home(fan_home):  # noqa: F811
    (fan_home / "secrets").mkdir()
    (fan_home / "secrets" / "fanvue.json").write_text(json.dumps(
        {"access_token": "a", "refresh_token": "r", "expires_at": 9e12, "scope": F.SCOPES}))
    return fan_home


def stock(home):
    """One of each accepted level: a level 1 preview, a nude and an xxx picture."""
    pre = accepted_picture(home, level=1, name="sheer.png", data=b"SHEER1")
    nude = accepted_picture(home, level=2, name="nude.png", data=b"NUDE1")
    xxx = accepted_picture(home, level=3, name="xxx.png", data=b"XXX1")
    return pre, nude, xxx


def test_nothing_to_drop_without_pictures_or_without_fanvue(home):
    assert D.plan(home) == []                                # no accepted pictures yet
    stock(home)
    (home / "secrets" / "fanvue.json").unlink()
    assert D.plan(home) == []                                # not connected


def test_a_weekly_drop_for_subscribers_and_one_for_vips(home):
    stock(home)
    rows = {r["kind"]: r for r in D.plan(home)}
    sub, vip = rows["subscribers"], rows["vip"]
    assert (sub["list"], sub["locked"], sub["preview"], sub["price_cents"]) == \
        ("subscribers", "nude.png", "sheer.png", 799)
    assert (vip["list"], vip["locked"], vip["preview"], vip["price_cents"]) == \
        ("spent_more_than_50", "xxx.png", None, 1299)
    assert D.plan(home) == list(rows.values())               # the same two, not new ones


def test_accept_sends_once_with_the_preview_free_and_the_set_locked(home):
    stock(home)
    sub = next(r for r in D.plan(home) if r["kind"] == "subscribers")
    fv = FakeFanvue()
    with pytest.raises(PermissionError):
        D.send(home, sub["drop_id"], fv, "agent:marketer")
    row = D.send(home, sub["drop_id"], fv, "human:owner")
    assert row["status"] == "SENT" and row["recipients"] == 7
    m = fv.sent[0]
    assert m["list"] == "subscribers" and m["price"] == 799 and m["key"] == sub["drop_id"]
    assert m["preview"] == "media-sheer.png" and "media-nude.png" in m["media"]
    with pytest.raises(D.DropError):
        D.send(home, sub["drop_id"], fv, "human:owner")       # never twice
    assert len(fv.sent) == 1


def test_hold_and_a_changed_picture_stop_a_drop(home):
    stock(home)
    sub = next(r for r in D.plan(home) if r["kind"] == "subscribers")
    (home / "artifacts" / "media" / "nude.png").write_bytes(b"SOMETHING ELSE")
    with pytest.raises(D.DropError, match="changed"):
        D.send(home, sub["drop_id"], FakeFanvue(), "human:owner")
    from bau.audit import AuditLog
    from bau.governor import Governor
    (home / "artifacts" / "media" / "nude.png").write_bytes(b"NUDE1")
    Governor(home, audit=AuditLog(home / "audit" / "chain.jsonl", key=b""),
             systemctl="").hold("test", by="human:owner")
    fv = FakeFanvue()
    with pytest.raises(D.DropError, match="HOLD"):
        D.send(home, sub["drop_id"], fv, "human:owner")
    assert fv.sent == [] and D.plan(home) == []              # no new cards during a HOLD


def test_no_new_drop_for_a_week_and_new_pictures_after_it(home):
    stock(home)
    now = dt.datetime.now(dt.UTC)
    for r in D.plan(home, now):
        D.skip(home, r["drop_id"], "human:owner")
    assert D.plan(home, now + dt.timedelta(days=3)) == []
    again = D.plan(home, now + dt.timedelta(days=8))
    assert {r["kind"] for r in again} == {"subscribers", "vip"}  # skipped pictures come back


def test_a_sent_drop_never_sells_the_same_picture_again(home):
    stock(home)
    now = dt.datetime.now(dt.UTC)
    sub = next(r for r in D.plan(home, now) if r["kind"] == "subscribers")
    D.send(home, sub["drop_id"], FakeFanvue(), "human:owner")
    later = [r for r in D.plan(home, now + dt.timedelta(days=8)) if r["kind"] == "subscribers"]
    assert later == []                                       # no new nude picture yet
    accepted_picture(home, level=2, name="nude2.png", data=b"NUDE2")
    accepted_picture(home, level=1, name="sheer2.png", data=b"SHEER2")
    later = [r for r in D.plan(home, now + dt.timedelta(days=8)) if r["kind"] == "subscribers"]
    assert later[0]["locked"] == "nude2.png" and later[0]["preview"] == "sheer2.png"


def test_a_failed_send_is_recorded_and_not_retried_by_itself(home):
    stock(home)
    sub = next(r for r in D.plan(home) if r["kind"] == "subscribers")
    with pytest.raises(F.FanvueError):
        D.send(home, sub["drop_id"], FakeFanvue(fail=True), "human:owner")
    row = next(r for r in D.all_drops(home) if r["drop_id"] == sub["drop_id"])
    assert row["status"] == "FAILED" and "500" in row["error"]


def test_the_client_sends_fanvues_mass_message_with_its_retry_key():
    class Http:
        def request(self, method, url, headers, body=None):
            self.got = (method, url, headers, json.loads(body))
            return 201, b'{"uuid": "mm-1", "recipientCount": 3}'
    fv = F.FanvueClient.__new__(F.FanvueClient)
    fv.http, fv.sleep = Http(), lambda s: None
    fv.access_token = lambda: "tok"
    fv.mass_message("subscribers", "hi", ["m1", "m2"], "m1", 799, key="dr_1")
    method, url, headers, body = fv.http.got
    assert (method, url) == ("POST", F.API + "/v1/chats/mass-messages")
    assert headers["Idempotency-Key"] == "dr_1"
    assert body == {"includedLists": {"smartListIds": ["subscribers"]}, "text": "hi",
                    "mediaUuids": ["m1", "m2"], "price": 799, "mediaPreviewUuid": "m1"}


def test_each_drop_is_a_click_only_card_in_jarvis(home, monkeypatch):
    from bau.assistant import Assistant
    stock(home)
    fv = FakeFanvue()
    monkeypatch.setattr(F, "FanvueClient", lambda h=None: fv)
    j = Assistant(home)
    cards = {j.pending[p["id"]].args["drop"]: p for p in j.setup_waiting()
             if p["tool"] == "fanvue_drop"}
    rows = {r["kind"]: r for r in D.all_drops(home)}
    sub, vip = cards[rows["subscribers"]["drop_id"]], cards[rows["vip"]["drop_id"]]
    assert "$7.99" in sub["summary"] and "free preview" in sub["summary"]
    assert "$12.99" in vip["summary"] and "spent more than $50" in vip["summary"]
    assert sub["preview"] and not sub["voice"] and not vip["voice"]   # explicit: click only
    assert j.confirm(sub["id"], True, "human:owner")["done"]
    j.confirm(vip["id"], False, "human:owner")
    assert {r["kind"]: r["status"] for r in D.all_drops(home)} == \
        {"subscribers": "SENT", "vip": "SKIPPED"}
    assert len(fv.sent) == 1 and fv.sent[0]["list"] == "subscribers"
    assert not [p for p in j.setup_waiting() if p["tool"] == "fanvue_drop"]   # gone
