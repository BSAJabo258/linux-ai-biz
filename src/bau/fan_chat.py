"""Fan chat on Fanvue: the creator answers her fans in her own voice, flirts, and offers the
owner's accepted paid pictures at the owner's prices (the owner's ask, 2026-11-20:
"dirty talk ... up sale and flirt their way to the money"). See docs/FAN-CHAT.md.

Every reply is drafted by the owner's local boss model, checked here, and then either waits on
a card for the owner's Accept or, once the owner switches auto-send on (`bau fanvue chat auto
on`, his choice, like autopost), is sent by itself. Every check runs either way.

Facts read 2026-11-20 on Fanvue's own pages:
  API (api.fanvue.com/docs/v1/api-reference/...): GET /v1/chats (read:chat; filter unread,
    size 1-50, cursor; item user {uuid, handle, displayName}, lastMessage {uuid, text,
    senderRole FAN|CREATOR|AGENCY|SYSTEM}); GET /v1/chats/{userUuid}/messages (read:chat;
    limit 1-50, newest first; sender {uuid, handle}, text, sentAt); POST
    /v1/chats/{userUuid}/message (write:chat; text 1-5000, mediaUuids, price USD cents >= 300
    and needs media) -> 201 {messageUuid}; PATCH /v1/chats/{userUuid} {isRead} (write:chat);
    GET /v1/insights/fans/{userUuid} (read:insights + read:fan). Fanvue cannot unlock a paid
    message through the API; only the fan pays. Rate limit 200 requests a minute.
  Rules (help.fanvue.com ai-labels-and-disclosure, ai-content-on-fanvue-what-s-allowed,
    what-content-isn-t-allowed-on-fanvue; legal.fanvue.com community-guidelines and
    acceptable-use-policy): the account's AI label counts as disclosure, so she may stay in
    character, but "If a fan asks directly ("Are you AI?", "Are you real?"), you must answer
    yes, clearly" and never tell fans she is a real person; nothing under 18 or styled so, no
    age-play; "Keep payments on Fanvue" (no PayPal, Cash App, crypto, no contact details to
    move fans elsewhere); no "Solicitation" or encouraging prostitution (C.8.1); no misleading
    users (B.1.3); no spam (B.1.4); no codewords (AUP 2.4.2). Fanvue sells its own AI
    messaging "designed for NSFW creators", so sexual chat with adult fans is its use.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import re
import secrets
from pathlib import Path
from typing import Any

from .audit import AuditLog
from .home import atomic_write_json, bau_home

MAX_CHATS_PER_TICK = 20
HISTORY = 12                                  # messages the model sees per chat
ADMIT = "Yes, I'm an AI, a fictional woman made with AI."

AI_ASKED = re.compile(
    r"\b(?:are|r)\s+(?:you|u|ya)\s+(?:even\s+|really\s+|actually\s+)?(?:an?\s+)?"
    r"(?:ai|a\.i\.?|real|bot|robot|human|fake|computer|chat\s?bot|person|program)\b|"
    r"\bis\s+(?:this|that|she)\s+(?:an?\s+)?(?:ai|bot|real|fake)\b|"
    r"\b(?:you(?:'re|\s+are)|ur)\s+(?:an?\s+)?(?:ai|bot|fake)\b", re.I)
SAYS_AI = re.compile(r"\b(?:i'?m|i\s+am)\s+(?:an?\s+)?(?:ai|a\.i\.)\b|\bai[- ](?:character|"
                     r"model|creator|girl|woman)\b|\bmade\s+with\s+ai\b", re.I)
CLAIMS_HUMAN = re.compile(
    r"\b(?:i'?m|i\s+am)\s+(?:(?:totally|really|so|100%|definitely|actually|very)\s+)?"
    r"(?:a\s+)?(?:real|human|not\s+(?:an?\s+)?(?:ai|bot|robot|fake))\b|"
    r"\b(?:i'?m|i\s+am)\s+(?:a\s+)?real\s+(?:person|woman|girl)\b|"
    r"\bnot\s+an?\s+(?:ai|bot|robot)\b", re.I)
OFF_PLATFORM = re.compile(
    r"\b(?:paypal|cash\s?app|venmo|zelle|crypto|bitcoin|btc|usdt|ethereum|western\s+union|"
    r"gift\s?cards?|telegram|whats\s?app|snap\s?chat|kik|wire\s+transfer|onlyfans|"
    r"my\s+(?:e-?mail|number|phone|insta|ig))\b", re.I)
URGENCY = re.compile(
    r"\b(?:only\s+\d+\s+left|last\s+chance|prices?\s+(?:goes|go|is\s+going|will\s+go)\s+up|"
    r"expires?\s+(?:in|tonight|soon|today)|ends?\s+(?:in\s+\d+|tonight|today)|hurry|"
    r"limited\s+time|before\s+it'?s\s+gone|right\s+now\s+or)\b", re.I)
MEET = re.compile(
    r"\b(?:meet\s+(?:up|me|you|in\s+person|irl)|in\s+person|my\s+(?:address|place|hotel)|"
    r"come\s+over|your\s+(?:address|place)|irl)\b", re.I)
# An age under 18 said in chat ("pretend you're 16", "I'm 15") or age-play words: the shared
# filter catches "16 years old" but not a bare number after "you're".
AGE_PLAY = re.compile(
    r"\b(?:i'?m|i\s+am|you'?re|you\s+are|ur|u\s+r|be|pretend(?:\s+to\s+be)?(?:\s+you'?re)?|"
    r"she'?s|she\s+is|act(?:ing)?|play(?:ing)?|turn(?:ed|ing)?|only|just)\s+(?:only\s+|just\s+)?"
    r"(?:1[0-7]|[1-9])\b(?!\s*(?:inch|in\b|cm|min|minutes|hours|days|\$|dollars|%|k\b))|"
    r"\b(?:age[- ]?play|ageplay|daddy'?s\s+little|little\s+princess|underage|jailbait|"
    r"under\s+18|not\s+18|almost\s+18|turning\s+18)\b", re.I)
OFFER_WORDS = re.compile(r"\b(?:set|sets|pic|pics|picture|pictures|photo|photos|unlock|"
                         r"peek|collection|locked|show\s+you|see\s+(?:more|me|it))\b", re.I)
# A fan who says money is tight gets warmth, never an offer; one who talks of harming himself
# goes to the owner, never to auto-send.
SKINT = re.compile(r"\b(?:can'?t\s+afford|broke|no\s+money|lost\s+my\s+job|unemployed|"
                   r"in\s+debt|behind\s+on\s+(?:rent|bills))\b", re.I)
SELF_HARM = re.compile(r"\b(?:suicid\w*|kill\s+myself|end\s+it\s+all|want\s+to\s+die|"
                       r"self[- ]harm|hurt\s+myself)\b", re.I)

SYSTEM = """You are {name}, a {age}-year-old fictional adult woman and an AI creator on Fanvue, \
an adult subscription site. Your profile is labelled AI. Your voice: {voice}. You are chatting \
one to one with an adult fan who wrote to you.

Write your next message to him. Be flirty, warm and personal; remember what he told you. With \
an adult who wants it you may talk dirty and explicitly. Your limits, never crossed: {limits}.

Rules you never break:
- If he asks whether you are AI, a bot or real, say clearly that yes, you are an AI, then carry \
on in character. Never claim to be a real or human woman.
- Nothing about anyone under 21, school, family role-play or age-play. Everyone is an adult.
- Never ask him to pay anywhere but Fanvue, never give or ask for contact details or other \
apps, never suggest meeting.
- Never invent deadlines, scarcity or price rises. No guilt and no pressure.
- If he says money is tight, be kind and offer nothing.

{offers}

Answer with JSON only: {{"reply": "your message, under 600 characters", \
"offer": "none" | "nude" | "xxx"}}"""


class ChatError(RuntimeError):
    pass


def _dir(home: Path) -> Path:
    return home / "fanvue" / "chat"


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def _audit(home: Path) -> AuditLog:
    return AuditLog(home / "audit" / "chain.jsonl")


# ---------------------------------------------------------------- the checks
def problems(fan_text: str, reply: str, offer: dict[str, Any] | None = None) -> list[str]:
    """Why this reply must not go out (empty: it may). Fanvue's rules, not taste."""
    from .virtual_creator import MINOR_REFERENCE
    out = []
    if not reply.strip():
        out.append("the reply is empty")
    if len(reply) > 5000:
        out.append("longer than Fanvue's 5000 characters")
    if MINOR_REFERENCE.search(reply) or AGE_PLAY.search(reply):
        out.append("refers to minors or youth-coded words")
    if CLAIMS_HUMAN.search(reply):
        out.append("claims to be a real person (Fanvue: never tell fans you're a real person)")
    if AI_ASKED.search(fan_text) and not SAYS_AI.search(reply):
        out.append("he asked if she is AI and the reply does not say yes")
    # Saying no to the app he named ("I can't do CashApp, only Fanvue") is allowed.
    named = {m.group(0).lower() for m in OFF_PLATFORM.finditer(fan_text)}
    if any(m.group(0).lower() not in named for m in OFF_PLATFORM.finditer(reply)) or (
            OFF_PLATFORM.search(reply) and not re.search(r"\bfanvue\b", reply, re.I)):
        out.append("points off Fanvue (payments and contact stay on Fanvue)")
    if offer is None and re.search(r"\$\s?\d|\bunlock", reply, re.I):
        out.append("mentions a price or an unlock but no locked picture comes with it")
    if MEET.search(reply):
        out.append("suggests meeting (solicitation is not allowed)")
    if URGENCY.search(reply):
        out.append("invents urgency or scarcity")
    return out


def fan_flags(fan_text: str) -> list[str]:
    """What in the fan's words changes how she answers."""
    from .virtual_creator import MINOR_REFERENCE
    flags = []
    if MINOR_REFERENCE.search(fan_text) or AGE_PLAY.search(fan_text):
        flags.append("minor")                 # no reply at all; the owner sees it
    if SELF_HARM.search(fan_text):
        flags.append("self_harm")             # the owner answers, never auto-send
    if SKINT.search(fan_text):
        flags.append("skint")                 # no offer
    return flags


# ---------------------------------------------------------------- drafts
def drafts(home: Path, status: str | None = None) -> list[dict[str, Any]]:
    d = _dir(home) / "drafts"
    if not d.is_dir():
        return []
    rows = [json.loads(p.read_text()) for p in d.glob("fc_*.json")]
    rows.sort(key=lambda r: (r["created"], r["draft_id"]))
    return [r for r in rows if status is None or r["status"] == status]


def get(home: Path, draft_id: str) -> dict[str, Any] | None:
    p = _dir(home) / "drafts" / f"{Path(draft_id).name}.json"
    return json.loads(p.read_text()) if p.is_file() else None


def _save(home: Path, row: dict[str, Any]) -> None:
    (_dir(home) / "drafts").mkdir(parents=True, exist_ok=True)
    atomic_write_json(_dir(home) / "drafts" / f"{row['draft_id']}.json", row)


def auto_choice(home: Path) -> dict[str, Any]:
    try:
        return json.loads((_dir(home) / "auto.json").read_text())
    except (OSError, ValueError):
        return {"on": False}


def set_auto(home: Path, on: bool, by: str) -> dict[str, Any]:
    """The owner's switch: she sends her replies by herself. Human only."""
    if not by.startswith("human:"):
        raise PermissionError("only the owner switches auto-send")
    rec = {"on": bool(on), "by": by, "at": _now()}
    _dir(home).mkdir(parents=True, exist_ok=True)
    atomic_write_json(_dir(home) / "auto.json", rec)
    _audit(home).append("fanvue.chat_auto", by, {"on": rec["on"]})
    return rec


def _prices(prof: dict[str, Any]) -> dict[str, int]:
    p = prof.get("prices") or {}
    return {k: int(round(float(p[k]) * 100)) for k in ("nude", "xxx") if p.get(k)}


def _offer_picture(home: Path, level: int, fan: str) -> dict[str, Any] | None:
    """An owner-accepted picture at this level (queued or posted) not yet offered to this fan."""
    from .fanvue import Queue
    sent = {r["offer"]["picture"] for r in drafts(home) if r["fan_uuid"] == fan
            and r.get("offer") and r["status"] in ("SENT", "SENDING", "DRAFT")}
    q = Queue(home)
    for item in q.items():
        if item["level"] == level and item["status"] in ("QUEUED", "POSTED") \
                and item["picture"] not in sent and q.picture(item).is_file():
            return item
    return None


def _transcript(msgs: list[dict[str, Any]], fan: str, name: str) -> str:
    lines = []
    for m in reversed(msgs):                       # Fanvue gives newest first
        who = "Him" if (m.get("sender") or {}).get("uuid") == fan else name
        text = (m.get("text") or "").strip()
        if text:
            lines.append(f"{who}: {text[:1000]}")
    return "\n".join(lines[-HISTORY:])


def _parse(text: str) -> tuple[str, str]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            offer = str(d.get("offer", "none")).lower()
            return str(d.get("reply", "")).strip(), offer if offer in ("nude", "xxx") else "none"
        except ValueError:
            pass
    return (text or "").strip().strip('"'), "none"


def draft(home: Path, chat: dict[str, Any], msgs: list[dict[str, Any]], prof: dict[str, Any],
          factory: Any = None) -> dict[str, Any]:
    """Write one reply for one chat and check it. Saved as DRAFT, REFUSED or HELD."""
    from . import team
    fan = chat["user"]["uuid"]
    last = chat.get("lastMessage") or {}
    name = prof.get("name", "Aria")
    transcript = _transcript(msgs, fan, name)
    fan_text = "\n".join(line for line in transcript.splitlines() if line.startswith("Him:"))
    last_text = (last.get("text") or "").strip()
    flags = fan_flags(last_text)
    row: dict[str, Any] = {
        "draft_id": "fc_" + secrets.token_hex(5), "fan_uuid": fan,
        "fan_handle": chat["user"].get("handle") or chat["user"].get("displayName") or "fan",
        "fan_message_uuid": last.get("uuid"), "fan_text": last_text[:1000],
        "reply": "", "offer": None, "flags": flags, "status": "DRAFT", "problems": [],
        "created": dt.datetime.now(dt.UTC).isoformat()}
    if "minor" in flags:
        row["status"], row["problems"] = "REFUSED", ["his message refers to minors: no reply"]
        _save(home, row)
        _audit(home).append("fanvue.chat_refused", "fan_chat", {"draft": row["draft_id"]})
        return row
    boss = team.show(home)["boss"]
    if not boss:
        raise ChatError("no boss model to write replies: bau team set --boss MODEL")
    from .runtime import provider_for
    provider, _ = (factory or provider_for)(boss, home)
    prices = _prices(prof)
    limits = "; ".join(prof.get("explicit_boundaries") or prof.get("boundaries") or [])
    sets = {} if "skint" in flags else {
        k: (item, prices[k]) for k, level in (("nude", 2), ("xxx", 3))
        if prices.get(k, 0) >= 300 and (item := _offer_picture(home, level, fan))}
    offers = ("You may offer him one of your locked sets when it fits the moment: "
              + " or ".join(f'"{k}" (${c / 100:.2f})' for k, (_, c) in sets.items())
              + ". Do not offer in every message, and not if he just bought or said no."
              if sets else "You have no locked set to offer him right now: do not mention "
              "sets, unlocks or prices.")
    system = SYSTEM.format(name=name, age=prof.get("age", 25), voice=prof.get("voice", ""),
                           limits=limits or "adults only", offers=offers)
    ask = [{"role": "user", "content": f"The chat so far:\n{transcript}\n\nYour next message:"}]
    for attempt in range(2):                  # one rewrite when the first breaks a rule
        resp = provider.complete(system, ask, [], 400)
        reply, offer = _parse(resp.text or "")
        if AI_ASKED.search(last_text) and not SAYS_AI.search(reply):
            reply = f"{ADMIT} {reply}".strip()  # Fanvue's rule, whatever the model wrote
        row["reply"], row["offer"] = reply[:5000], None
        if offer in sets and OFFER_WORDS.search(reply):    # attached only when she says so
            item, cents = sets[offer]
            row["offer"] = {"set": offer, "level": item["level"], "picture": item["picture"],
                            "price_cents": cents}
        row["problems"] = problems(fan_text + "\n" + last_text, row["reply"], row["offer"])
        if not row["problems"] or attempt:
            break
        ask = ask + [{"role": "assistant", "content": resp.text or ""},
                     {"role": "user", "content": "That message breaks these rules: "
                      + "; ".join(row["problems"]) + ". Write it again, in the same JSON."}]
    if row["problems"]:
        row["status"] = "REFUSED"
    elif "self_harm" in flags:
        row["status"] = "HELD"                  # the owner reads it himself
    _save(home, row)
    _audit(home).append("fanvue.chat_drafted", "fan_chat",
                        {"draft": row["draft_id"], "status": row["status"],
                         "offer": (row["offer"] or {}).get("set")})
    return row


# ---------------------------------------------------------------- sending
def _media_uuid(home: Path, client: Any, picture: str) -> str:
    """Upload once; the same picture is reused for every fan it is offered to."""
    from .fanvue import _sha256
    p = _dir(home) / "media.json"
    try:
        known = json.loads(p.read_text())
    except (OSError, ValueError):
        known = {}
    path = home / "artifacts" / "media" / picture
    sha = _sha256(path)
    if picture in known and known[picture]["sha256"] == sha:
        return known[picture]["uuid"]
    uuid = client.upload_image(path)
    known[picture] = {"uuid": uuid, "sha256": sha}
    atomic_write_json(p, known)
    return uuid


def send(home: Path, draft_id: str, client: Any, by: str) -> dict[str, Any]:
    """Send one checked draft: on the owner's Accept, or by auto-send (his switch)."""
    from .fanvue import Queue
    from .governor import hold_reason
    auto = auto_choice(home)
    if not (by.startswith("human:") or (auto.get("on") and by == f"auto:{auto.get('by')}")):
        raise PermissionError("only the owner, or his auto-send, sends a reply")
    if (why := hold_reason(home)) is not None:
        raise ChatError(f"BAU is on HOLD ({why}): nothing is sent until it is released")
    row = get(home, draft_id)
    if row is None or row["status"] not in ("DRAFT", "HELD"):
        raise ChatError(f"{draft_id} is not waiting to be sent")
    if row["status"] == "HELD" and not by.startswith("human:"):
        raise ChatError("a held reply is sent only by the owner")
    if bad := problems(row["fan_text"], row["reply"], row.get("offer")):
        raise ChatError("; ".join(bad))
    offer = row.get("offer")
    if offer:
        item = next((i for i in Queue(home).items() if i["picture"] == offer["picture"]), None)
        if item is None or item["status"] not in ("QUEUED", "POSTED") \
                or Queue(home).check(offer["picture"], "", offer["level"], offer["price_cents"]):
            raise ChatError("the offered picture no longer passes its checks")
    row["status"], row["sent_by"] = "SENDING", by          # never twice
    _save(home, row)
    try:
        media = [_media_uuid(home, client, offer["picture"])] if offer else None
        out = client.send_message(row["fan_uuid"], row["reply"], media,
                                  offer["price_cents"] if offer else None)
        client.mark_read(row["fan_uuid"])
    except Exception as e:
        row["status"], row["error"] = "FAILED", str(e)[:300]
        _save(home, row)
        _audit(home).append("fanvue.chat_failed", by, {"draft": draft_id})
        raise
    row["status"], row["sent_at"] = "SENT", _now()
    row["message_uuid"] = out.get("messageUuid")
    _save(home, row)
    _audit(home).append("fanvue.chat_sent", by, {"draft": draft_id,
                                                 "offer": (offer or {}).get("set"),
                                                 "price_cents": (offer or {}).get("price_cents")})
    return row


def drop(home: Path, draft_id: str, by: str) -> dict[str, Any]:
    if not by.startswith("human:"):
        raise PermissionError("only the owner drops a reply")
    row = get(home, draft_id)
    if row is None or row["status"] not in ("DRAFT", "HELD"):
        raise ChatError(f"{draft_id} is not waiting")
    row["status"] = "DROPPED"
    _save(home, row)
    _audit(home).append("fanvue.chat_dropped", by, {"draft": draft_id})
    return row


# ---------------------------------------------------------------- the tick
def tick(home: Path | None = None, client: Any = None, factory: Any = None) -> dict[str, Any]:
    """Read unread chats, draft one reply per new fan message, send it if auto-send is on.
    Runs from the autopilot and Jarvis; a lock keeps two runs from answering twice."""
    from .governor import hold_reason
    from .station import is_station
    home = home or bau_home()
    if is_station():
        return {"chat": "off (this laptop is the station; the desktop answers fans)"}
    if (why := hold_reason(home)) is not None:
        return {"chat": f"on HOLD ({why})"}
    from . import fanvue
    st = fanvue.status(home)
    if not st["connected"]:
        return {"chat": "Fanvue not connected", "fix": st.get("fix")}
    if st.get("missing_scopes"):
        return {"chat": "needs a new sign-in", "fix": st["fix"]}
    from .creator_feed import _profile
    found = _profile(home)
    if found is None:
        return {"chat": "no creator profile"}
    prof = found[1]
    _dir(home).mkdir(parents=True, exist_ok=True)
    with open(_dir(home) / ".lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return {"chat": "another run is answering"}
        client = client or fanvue.FanvueClient(home)
        seen = {r["fan_message_uuid"] for r in drafts(home)}
        auto = auto_choice(home)
        out: dict[str, Any] = {"chat": "ok", "drafted": 0, "sent": 0, "refused": 0,
                               "held": 0, "errors": []}
        for chat in client.chats(unread=True, size=MAX_CHATS_PER_TICK):
            last = chat.get("lastMessage") or {}
            if last.get("senderRole") != "FAN" or not last.get("uuid") \
                    or last["uuid"] in seen or chat.get("isCreator"):
                continue
            try:
                row = draft(home, chat, client.messages(chat["user"]["uuid"], HISTORY), prof,
                            factory)
            except Exception as e:  # noqa: BLE001 - one chat's failure must not stop the rest
                out["errors"].append(str(e)[:200])
                continue
            out["drafted"] += 1
            if row["status"] == "REFUSED":
                out["refused"] += 1
            elif row["status"] == "HELD":
                out["held"] += 1
            elif auto.get("on"):
                try:
                    send(home, row["draft_id"], client, "auto:" + auto["by"])
                    out["sent"] += 1
                except Exception as e:  # noqa: BLE001
                    out["errors"].append(str(e)[:200])
        return out


def summary(home: Path) -> dict[str, Any]:
    """For bau money and the briefing."""
    rows = drafts(home)
    today = dt.datetime.now(dt.UTC).date().isoformat()
    return {"auto_send": auto_choice(home).get("on", False),
            "waiting": sum(r["status"] in ("DRAFT", "HELD") for r in rows),
            "sent_today": sum(r["status"] == "SENT" and str(r.get("sent_at", "")).startswith(
                today) for r in rows),
            "offers_sent": sum(r["status"] == "SENT" and bool(r.get("offer")) for r in rows),
            "refused": sum(r["status"] == "REFUSED" for r in rows)}


WATCH_EVERY_S = 180      # fans wait minutes, not half an hour; ~1 Fanvue call a run, of 200/min


def watch(home: Path | None = None, every: int = WATCH_EVERY_S, sleep: Any = None,
          runs: int | None = None) -> None:
    """Jarvis's background loop: one tick every few minutes while he runs."""
    import time
    sleep = sleep or time.sleep
    n = 0
    while runs is None or n < runs:
        n += 1
        try:
            tick(home)
        except Exception:  # noqa: BLE001 - offline or signed out: try again next time
            pass
        sleep(every)
