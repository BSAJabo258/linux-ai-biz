"""Weekly drops on Fanvue (the owner's plan, accepted 2026-11-20, week 3: "a sheer free
preview with the nude set locked behind it; to the VIP list the XXX set first"). See
docs/DROPS.md.

Once a week Jarvis proposes two locked messages, each on its own card with the picture:
  subscribers  a free preview (an accepted level 1 picture, no nudity) and an accepted level 2
               picture locked behind it at the owner's nude price;
  VIPs         an accepted level 3 picture at the owner's xxx price, to Fanvue's "Spent more
               than $50" list.
Accept sends it once; Not now skips it until next week. Only the owner's click sends a drop;
HOLD stops it; every picture's age check and every text rule of fan chat run again at send.

Facts read 2026-11-21 on Fanvue's own API pages (api.fanvue.com/docs):
  POST /v1/chats/mass-messages (scopes write:chat, read:fan): body includedLists
    {smartListIds, customListUuids, dynamicSmartListUuids} (required), text 1-5000,
    mediaUuids (max 2000), mediaPreviewUuid ("shown for free as a preview of a pay-to-view mass
    message. Requires a price and attached media"), price (x >= 300, USD cents), excludedLists,
    scheduledAt; header Idempotency-Key ("Reuse the same key on a retry ... a key reused for a
    different message is rejected with 409", remembered 24 hours) -> 201 {uuid, publishedAt,
    recipientCount, status SENT|UNSENT|SENDING|FAILED|MODERATED|SCHEDULED}.
  Smart list ids (get-smart-lists): subscribers, auto_renewing, non_renewing, followers,
    free_trial_subscribers, expired_subscribers, spent_more_than_50, muted, creators.
"""

from __future__ import annotations

import datetime as dt
import json
import secrets
from pathlib import Path
from typing import Any

from .audit import AuditLog
from .home import atomic_write_json

EVERY = dt.timedelta(days=7)
# kind: (smart list, level locked behind it, price key in the profile, level of the preview)
KINDS = {"subscribers": ("subscribers", 2, "nude", 1),
         "vip": ("spent_more_than_50", 3, "xxx", None)}
TEXTS = {
    "subscribers": ("My new set is here 💋 The first picture is yours to see; the rest of it is "
                    "waiting for you behind the lock."),
    "vip": ("You've been so good to me, so you get this one first 😘 My most private set, just "
            "for my favourite fans."),
}


class DropError(RuntimeError):
    pass


def _path(home: Path) -> Path:
    return home / "fanvue" / "drops.json"


def all_drops(home: Path) -> list[dict[str, Any]]:
    try:
        return json.loads(_path(home).read_text())
    except (OSError, ValueError):
        return []


def _save(home: Path, rows: list[dict[str, Any]]) -> None:
    atomic_write_json(_path(home), rows)


def _now(now: dt.datetime | None = None) -> dt.datetime:
    return now or dt.datetime.now(dt.UTC)


def _ready(home: Path) -> tuple[Path, dict[str, Any]] | None:
    """The creator's profile, when Fanvue is connected, nothing is on HOLD and this computer
    does the work (not the laptop station)."""
    from . import fanvue
    from .creator_feed import _profile
    from .governor import hold_reason
    from .station import is_station
    if is_station() or hold_reason(home) is not None:
        return None
    if fanvue.TokenStore(home).store.state() != "present":
        return None
    return _profile(home)


def _pick(home: Path, level: int, used: set[str]) -> dict[str, Any] | None:
    """An owner-accepted picture at this level that passes its checks and no drop used yet;
    one not posted on her feed first."""
    from .fanvue import Queue
    q = Queue(home)
    fit = [i for i in q.items() if i["level"] == level and i["status"] in ("QUEUED", "POSTED")
           and i["picture"] not in used and q.picture(i).is_file()
           and not q.check(i["picture"], "", level, i.get("price_cents") or 300)]
    fit.sort(key=lambda i: i["status"] != "QUEUED")
    return fit[0] if fit else None


def plan(home: Path, now: dt.datetime | None = None) -> list[dict[str, Any]]:
    """This week's drops waiting for the owner, proposing any that are due. Reads only files."""
    found = _ready(home)
    rows = all_drops(home)
    if found is None:
        return []
    _, prof = found
    prices = prof.get("prices") or {}
    changed = False
    for kind, (smart, level, key, preview_level) in KINDS.items():
        mine = [r for r in rows if r["kind"] == kind]
        if any(r["status"] == "PROPOSED" for r in mine):
            continue
        last = max((r["created_at"] for r in mine), default="")
        if last and _now(now) - dt.datetime.fromisoformat(last) < EVERY:
            continue
        if not prices.get(key):
            continue                               # the owner's price first (prices card)
        sold = [r for r in rows if r["status"] != "SKIPPED"]    # a skipped drop frees them
        used = {r["locked"] for r in sold} | {r["preview"] for r in sold if r.get("preview")}
        locked = _pick(home, level, used)
        preview = _pick(home, preview_level, used) if preview_level is not None else None
        if locked is None or (preview_level is not None and preview is None):
            continue                               # nothing new to sell this week
        rows.append({"drop_id": "dr_" + secrets.token_hex(5), "kind": kind, "list": smart,
                     "locked": locked["picture"], "level": level,
                     "preview": preview["picture"] if preview else None,
                     "price_cents": int(round(float(prices[key]) * 100)),
                     "text": TEXTS[kind], "status": "PROPOSED",
                     "created_at": _now(now).isoformat()})
        changed = True
    if changed:
        _save(home, rows)
    return [r for r in rows if r["status"] == "PROPOSED"]


def problems(home: Path, row: dict[str, Any]) -> list[str]:
    """Why this drop must not go out now (empty: it may)."""
    from .fan_chat import problems as text_problems
    from .fanvue import MIN_PRICE_CENTS, Queue
    q = Queue(home)
    out = text_problems("", row["text"], offer={"price_cents": row["price_cents"]})
    if row["price_cents"] < MIN_PRICE_CENTS:
        out.append("the price is under Fanvue's $3.00")
    for picture, level in ((row["locked"], row["level"]), (row.get("preview"), 1)):
        if picture is None:
            continue
        item = next((i for i in q.items() if i["picture"] == picture), None)
        if item is None or item["status"] not in ("QUEUED", "POSTED"):
            out.append(f"{picture} is no longer an accepted picture")
        else:
            out += q.check(picture, row["text"], level, row["price_cents"])
    return out


def send(home: Path, drop_id: str, client: Any, by: str) -> dict[str, Any]:
    """Only on the owner's Accept. Sent once: a retry reuses the drop's key."""
    from .fan_chat import _media_uuid
    from .governor import hold_reason
    if not by.startswith("human:"):
        raise PermissionError("only the owner sends a drop")
    if (why := hold_reason(home)) is not None:
        raise DropError(f"BAU is on HOLD ({why}): nothing is sent until it is released")
    rows = all_drops(home)
    row = next((r for r in rows if r["drop_id"] == drop_id), None)
    if row is None or row["status"] != "PROPOSED":
        raise DropError(f"{drop_id} is not waiting to be sent")
    if bad := problems(home, row):
        raise DropError("; ".join(bad))
    row["status"], row["sent_by"] = "SENDING", by          # never twice
    _save(home, rows)
    audit = AuditLog(home / "audit" / "chain.jsonl")
    try:
        locked = _media_uuid(home, client, row["locked"])
        preview = _media_uuid(home, client, row["preview"]) if row.get("preview") else None
        media = [preview, locked] if preview else [locked]
        out = client.mass_message(row["list"], row["text"], media, preview,
                                  row["price_cents"], key=drop_id)
    except Exception as e:
        row["status"], row["error"] = "FAILED", str(e)[:300]
        _save(home, rows)
        audit.append("fanvue.drop_failed", by, {"drop": drop_id})
        raise
    row.update(status="SENT", sent_at=_now().isoformat(), message_uuid=out.get("uuid"),
               recipients=out.get("recipientCount"), fanvue_status=out.get("status"))
    _save(home, rows)
    audit.append("fanvue.drop_sent", by, {"drop": drop_id, "list": row["list"],
                                          "price_cents": row["price_cents"],
                                          "recipients": out.get("recipientCount")})
    return row


def skip(home: Path, drop_id: str, by: str) -> dict[str, Any]:
    """Not now: this week's drop is skipped; next week's comes with new pictures."""
    if not by.startswith("human:"):
        raise PermissionError("only the owner skips a drop")
    rows = all_drops(home)
    row = next((r for r in rows if r["drop_id"] == drop_id), None)
    if row is None or row["status"] != "PROPOSED":
        raise DropError(f"{drop_id} is not waiting")
    row["status"] = "SKIPPED"
    _save(home, rows)
    AuditLog(home / "audit" / "chain.jsonl").append("fanvue.drop_skipped", by,
                                                    {"drop": drop_id})
    return row
