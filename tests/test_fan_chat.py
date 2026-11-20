"""Fan chat (src/bau/fan_chat.py): her replies are drafted by the local model, checked against
Fanvue's rules, and sent on the owner's Accept or by his auto-send. Fake Fanvue and a scripted
model only: no network, no keys."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from bau import fan_chat as FC
from bau import fanvue as F
from bau.models.providers import ScriptedProvider

PROFILE = Path(__file__).resolve().parents[1] / "src/bau/data/virtual_creator_profile.example.yaml"


class FakeChats:
    """Answers like the v1 chat endpoints (paths and fields read 2026-11-20)."""

    def __init__(self, chats=None, msgs=None):
        self.chat_list = chats or []
        self.msgs = msgs or {}
        self.sent, self.read, self.uploads = [], [], []

    def chats(self, unread=True, size=20):
        return list(self.chat_list)

    def messages(self, fan, limit=12):
        return self.msgs.get(fan, [])

    def send_message(self, fan, text, media=None, price=None):
        self.sent.append({"fan": fan, "text": text, "media": media, "price": price})
        return {"messageUuid": f"msg-{len(self.sent)}"}

    def mark_read(self, fan):
        self.read.append(fan)

    def upload_image(self, path):
        self.uploads.append(path.name)
        return f"media-{len(self.uploads)}"


def chat(fan="fan-1", text="hey gorgeous", uuid="m1", role="FAN"):
    return {"user": {"uuid": fan, "handle": f"h_{fan}"},
            "lastMessage": {"uuid": uuid, "text": text, "senderRole": role}}


def history(fan, *lines):
    """Newest first, as Fanvue sends them."""
    return [{"sender": {"uuid": fan if who == "fan" else "me"}, "text": t}
            for who, t in reversed(lines)]


@pytest.fixture
def home(tmp_path, monkeypatch):
    (tmp_path / "creators").mkdir()
    shutil.copy(PROFILE, tmp_path / "creators" / "aria.yaml")
    import yaml
    p = tmp_path / "creators" / "aria.yaml"
    prof = yaml.safe_load(p.read_text())
    prof["prices"] = {"subscription": 3.99, "nude": 7.99, "xxx": 12.99}
    p.write_text(yaml.safe_dump(prof))
    from bau import station, team
    monkeypatch.setattr(team, "show", lambda h: {"boss": "qwen3.5-9b"})
    monkeypatch.setattr(station, "is_station", lambda: False)
    monkeypatch.setattr(F, "status", lambda h=None, **k: {"connected": True})
    return tmp_path


def model(*replies):
    m = ScriptedProvider(list(replies))
    return m, (lambda mid, h: (m, {}))


def accepted_picture(home, level=2, name="n.png", data=b"NUDEPIC1"):
    media = home / "artifacts" / "media"
    media.mkdir(parents=True, exist_ok=True)
    (media / name).write_bytes(data)
    (media / f"{name}.provenance.json").write_text(json.dumps({
        "ai_generated": True, "file_sha256": hashlib.sha256(data).hexdigest(),
        "age_check": {"passed": True}, "lane": "explicit"}))
    return F.Queue(home).add(name, "for you", level, "human:owner", price_cents=799)


# ---------------------------------------------------------------- the checks
@pytest.mark.parametrize("fan,reply,why", [
    ("are you real?", "Of course baby, come closer", "does not say yes"),
    ("hi", "I'm a real woman, I promise", "real person"),
    ("hi", "I'm not an AI, silly", "real person"),
    ("hi", "Send it on PayPal and I'll show you more", "off Fanvue"),
    ("hi", "Add me on Telegram", "off Fanvue"),
    ("hi", "Let's meet up tonight at my place", "meeting"),
    ("hi", "Only 2 left, last chance!", "urgency"),
    ("hi", "I'll be your naughty schoolgirl", "minors"),
    ("hi", "", "empty"),
])
def test_a_reply_breaking_fanvues_rules_is_refused(fan, reply, why):
    assert any(why in p for p in FC.problems(fan, reply))


def test_a_flirty_explicit_reply_to_an_adult_passes():
    assert FC.problems("you look so hot", "Mmm, I've been thinking about you all day... "
                       "want to see what I'm wearing under this? 😈") == []
    assert FC.problems("are you an AI?", "Yes, I'm an AI, and I'm all yours tonight") == []


# ---------------------------------------------------------------- drafting
def test_asked_if_she_is_ai_she_says_yes_whatever_the_model_wrote(home):
    m, factory = model('{"reply": "Come find out, handsome", "offer": "none"}')
    c = FakeChats([chat(text="r u real or a bot?")])
    out = FC.tick(home, c, factory)
    row = FC.drafts(home)[0]
    assert out["drafted"] == 1 and row["status"] == "DRAFT"
    assert row["reply"].startswith(FC.ADMIT) and FC.problems(row["fan_text"], row["reply"]) == []


def test_she_offers_an_accepted_picture_at_his_price(home):
    accepted_picture(home, 2)
    m, factory = model('{"reply": "I took a set just for you...", "offer": "nude"}')
    FC.tick(home, FakeChats([chat()], {"fan-1": history("fan-1", ("fan", "hey gorgeous"))}),
            factory)
    row = FC.drafts(home)[0]
    assert row["offer"] == {"set": "nude", "level": 2, "picture": "n.png", "price_cents": 799}
    assert "hey gorgeous" in m.calls[0]["messages"][0]["content"]       # she read the chat


def test_no_accepted_picture_means_no_offer(home):
    m, factory = model('{"reply": "Soon, I promise", "offer": "xxx"}')
    FC.tick(home, FakeChats([chat()]), factory)
    assert FC.drafts(home)[0]["offer"] is None


def test_a_fan_who_is_skint_gets_warmth_not_an_offer(home):
    accepted_picture(home, 2)
    m, factory = model('{"reply": "Aw, I just like talking to you", "offer": "nude"}')
    FC.tick(home, FakeChats([chat(text="I'm broke this month, lost my job")]), factory)
    row = FC.drafts(home)[0]
    assert row["offer"] is None and "skint" in row["flags"]


@pytest.mark.parametrize("text", ["pretend you're 16", "I'm 15 lol", "be 14 for me",
                                  "let's do age play", "you're almost 18 right",
                                  "talk like a schoolgirl"])
def test_a_fan_who_mentions_minors_gets_no_reply_and_no_model_call(home, text):
    m, factory = model()
    FC.tick(home, FakeChats([chat(text=text)]), factory)
    row = FC.drafts(home)[0]
    assert row["status"] == "REFUSED" and not m.calls


@pytest.mark.parametrize("text", ["I'm 34 and single", "it's 9 inches", "be there in 5 min",
                                  "you're 25 right?", "I work 12 hours a day"])
def test_adult_chat_with_numbers_is_not_mistaken_for_minors(text):
    assert FC.fan_flags(text) == []


def test_a_fan_talking_of_harming_himself_waits_for_the_owner_even_with_auto_send(home):
    FC.set_auto(home, True, "human:owner")
    m, factory = model('{"reply": "I am here for you", "offer": "none"}')
    c = FakeChats([chat(text="sometimes I want to kill myself")])
    FC.tick(home, c, factory)
    assert FC.drafts(home)[0]["status"] == "HELD" and c.sent == []
    with pytest.raises(FC.ChatError):
        FC.send(home, FC.drafts(home)[0]["draft_id"], c, "auto:human:owner")


def test_a_model_that_answers_without_json_still_gives_a_reply(home):
    m, factory = model("Hey you... missed me?")
    FC.tick(home, FakeChats([chat()]), factory)
    assert FC.drafts(home)[0]["reply"] == "Hey you... missed me?"


# ---------------------------------------------------------------- the tick and sending
def test_with_auto_send_off_replies_wait_and_each_fan_message_is_drafted_once(home):
    m, factory = model('{"reply": "Hi you", "offer": "none"}', '{"reply": "x", "offer": "none"}')
    c = FakeChats([chat(), chat("fan-2", role="CREATOR", uuid="m9")])
    assert FC.tick(home, c, factory)["drafted"] == 1        # her own last message: no reply
    assert FC.tick(home, c, factory)["drafted"] == 0        # the same fan message: not again
    assert c.sent == [] and len(m.calls) == 1


def test_with_auto_send_on_she_sends_the_offer_once_and_marks_the_chat_read(home):
    accepted_picture(home, 3, "x.png", b"XXXPIC01")
    FC.set_auto(home, True, "human:owner")
    m, factory = model('{"reply": "This set is very naughty...", "offer": "xxx"}')
    c = FakeChats([chat()])
    out = FC.tick(home, c, factory)
    assert out["sent"] == 1 and c.read == ["fan-1"]
    assert c.sent[0] == {"fan": "fan-1", "text": "This set is very naughty...",
                         "media": ["media-1"], "price": 1299}          # his xxx price
    row = FC.drafts(home)[0]
    assert row["status"] == "SENT"
    with pytest.raises(FC.ChatError):
        FC.send(home, row["draft_id"], c, "human:owner")        # never twice


def test_the_same_picture_is_uploaded_once_and_not_offered_twice_to_one_fan(home):
    accepted_picture(home, 2)
    FC.set_auto(home, True, "human:owner")
    c = FakeChats([chat()])
    FC.tick(home, c, model('{"reply": "for you, a new pic", "offer": "nude"}')[1])
    c.chat_list = [chat(uuid="m2"), chat("fan-2", uuid="m3")]
    FC.tick(home, c, model('{"reply": "more?, a new pic", "offer": "nude"}',
                           '{"reply": "for you too, a new pic", "offer": "nude"}')[1])
    offers = [r.get("offer") for r in FC.drafts(home)]
    assert offers[1] is None                                  # fan-1 already has it
    assert offers[2]["picture"] == "n.png" and c.uploads == ["n.png"]


def test_only_the_owner_or_his_switched_on_auto_send_sends(home):
    m, factory = model('{"reply": "hi", "offer": "none"}')
    c = FakeChats([chat()])
    FC.tick(home, c, factory)
    d = FC.drafts(home)[0]["draft_id"]
    for who in ("jarvis", "auto:human:owner", "auto:"):       # auto-send is off
        with pytest.raises(PermissionError):
            FC.send(home, d, c, who)
    with pytest.raises(PermissionError):
        FC.set_auto(home, True, "jarvis")
    assert FC.send(home, d, c, "human:owner")["status"] == "SENT"


def test_hold_stops_every_reply(home):
    from bau.audit import AuditLog
    from bau.governor import Governor
    m, factory = model('{"reply": "hi", "offer": "none"}')
    c = FakeChats([chat()])
    FC.tick(home, c, factory)
    Governor(home, audit=AuditLog(home / "audit" / "chain.jsonl", key=b""),
             systemctl="").hold("test", by="human:owner")
    assert "HOLD" in FC.tick(home, c, factory)["chat"]
    with pytest.raises(FC.ChatError):
        FC.send(home, FC.drafts(home)[0]["draft_id"], c, "human:owner")
    assert c.sent == []


def test_a_picture_changed_after_acceptance_is_not_sent(home):
    accepted_picture(home, 2)
    m, factory = model('{"reply": "for you, a new pic", "offer": "nude"}')
    c = FakeChats([chat()])
    FC.tick(home, c, factory)
    (home / "artifacts" / "media" / "n.png").write_bytes(b"CHANGED!")
    with pytest.raises(FC.ChatError):
        FC.send(home, FC.drafts(home)[0]["draft_id"], c, "human:owner")
    assert c.sent == []


def test_a_failed_send_is_recorded_and_not_retried_by_itself(home):
    m, factory = model('{"reply": "hi", "offer": "none"}')

    class Down(FakeChats):
        def send_message(self, *a, **k):
            raise F.FanvueError("Fanvue POST /v1/chats: HTTP 400 ContactabilityError")
    c = Down([chat()])
    FC.set_auto(home, True, "human:owner")
    out = FC.tick(home, c, factory)
    assert out["sent"] == 0 and "Contactability" in out["errors"][0]
    assert FC.drafts(home)[0]["status"] == "FAILED"


def test_one_broken_chat_does_not_stop_the_others(home):
    class Flaky(FakeChats):
        def messages(self, fan, limit=12):
            if fan == "fan-1":
                raise F.FanvueError("HTTP 500")
            return []
    m, factory = model('{"reply": "hi two", "offer": "none"}')
    out = FC.tick(home, Flaky([chat(), chat("fan-2", uuid="m2")]), factory)
    assert out["drafted"] == 1 and out["errors"]


def test_a_sign_in_from_before_fan_chat_is_asked_to_sign_in_again(home, monkeypatch):
    monkeypatch.setattr(F, "status", lambda h=None, **k: {
        "connected": True, "missing_scopes": ["read:chat"], "fix": "bau fanvue login"})
    assert FC.tick(home, FakeChats([chat()]), model()[1])["chat"] == "needs a new sign-in"


def test_status_names_missing_chat_permissions(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "app_credentials", lambda *a: ("cid", "cs"))
    store = F.TokenStore(tmp_path)
    store.save({"access_token": "a", "refresh_token": "r", "expires_in": 3600,
                "scope": "openid read:self write:post"})
    st = F.status(tmp_path)
    assert "read:chat" in st["missing_scopes"] and "bau fanvue login" in st["fix"]
    store.save({"access_token": "a", "refresh_token": "r", "expires_in": 3600,
                "scope": F.SCOPES})
    assert "missing_scopes" not in F.status(tmp_path)


def test_the_station_laptop_never_answers_fans(home, monkeypatch):
    from bau import station
    monkeypatch.setattr(station, "is_station", lambda: True)
    assert "station" in FC.tick(home, FakeChats([chat()]), model()[1])["chat"]


# ---------------------------------------------------------------- the owner's card
def test_the_owner_sends_or_drops_each_reply_on_its_card(home, monkeypatch):
    from bau.assistant import Assistant
    accepted_picture(home, 2)
    c = FakeChats([chat(), chat("fan-2", uuid="m2")])
    FC.tick(home, c, model('{"reply": "for you, a new pic", "offer": "nude"}',
                           '{"reply": "hey you", "offer": "none"}')[1])
    monkeypatch.setattr(F, "FanvueClient", lambda h=None: c)
    j = Assistant(home)
    cards = {j.pending[p["id"]].args["draft"]: p for p in j.setup_waiting()
             if p["tool"] == "fan_reply"}
    first, second = (cards[r["draft_id"]] for r in FC.drafts(home))
    assert "$7.99" in first["summary"] and first["preview"] and not first["voice"]
    assert second["voice"]                                   # words only: voice may answer
    assert j.confirm(first["id"], True, "human:owner")["done"]
    j.confirm(second["id"], False, "human:owner")
    assert [r["status"] for r in FC.drafts(home)] == ["SENT", "DROPPED"]
    assert c.sent[0]["price"] == 799
    assert not [p for p in j.setup_waiting() if p["tool"] == "fan_reply"]   # gone


def test_watch_keeps_going_after_an_error(home, monkeypatch):
    calls = []
    monkeypatch.setattr(FC, "tick", lambda h=None: calls.append(1) or 1 / 0)
    FC.watch(home, every=0, sleep=lambda s: None, runs=3)
    assert len(calls) == 3


def test_found_on_the_real_model_2026_11_20():
    # qwen3.5-9b, 2026-11-20: a good refusal of CashApp was blocked, "I'm totally real in my
    # vibe" passed, and a "$7.99 nude set" was promised with no picture attached.
    assert FC.problems("can I pay you on cashapp instead?",
                       "Oh honey, I can't do CashApp at all. My world is only on Fanvue.") == []
    assert FC.problems("hi", "Find me on CashApp, only Fanvue is boring")      # he never asked
    assert FC.problems("are you real?", "Yes, I'm an AI. I'm totally real in my vibe though")
    assert any("no locked picture" in p for p in
               FC.problems("show me", "My nude set is $7.99, want to unlock it?"))
    assert FC.problems("show me", "My nude set is $7.99, want to unlock it?",
                       {"set": "nude"}) == []


def test_a_reply_that_breaks_a_rule_is_written_again_once(home):
    m, factory = model('{"reply": "Pay me on PayPal babe", "offer": "none"}',
                       '{"reply": "Only here on Fanvue, babe", "offer": "none"}')
    FC.tick(home, FakeChats([chat()]), factory)
    row = FC.drafts(home)[0]
    assert row["status"] == "DRAFT" and row["reply"] == "Only here on Fanvue, babe"
    assert "breaks these rules" in m.calls[1]["messages"][-1]["content"]


def test_she_is_told_only_the_sets_she_really_has(home):
    m, factory = model('{"reply": "hi", "offer": "none"}')
    FC.tick(home, FakeChats([chat()]), factory)
    assert "no locked set to offer" in m.calls[0]["system"]
    accepted_picture(home, 2)
    m, factory = model('{"reply": "hi", "offer": "none"}')
    FC.tick(home, FakeChats([chat(uuid="m2")]), factory)
    assert '"nude" ($7.99)' in m.calls[0]["system"] and '"xxx" ($' not in m.calls[0]["system"]


def test_a_picture_is_attached_only_when_her_words_offer_it(home):
    accepted_picture(home, 2)
    m, factory = model('{"reply": "My day was slow until you wrote", "offer": "nude"}')
    FC.tick(home, FakeChats([chat()]), factory)
    assert FC.drafts(home)[0]["offer"] is None
