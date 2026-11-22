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

import contextlib
import datetime as dt
import fcntl
import json
import secrets
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .audit import AuditLog
from .home import atomic_write_json

EVERY = dt.timedelta(days=7)
# Fanvue remembers a send's Idempotency-Key for 24 hours: inside that window a failed or
# interrupted drop is offered again and retried with the same key (never sent twice).
RETRY_WINDOW = dt.timedelta(hours=23)
STUCK = dt.timedelta(minutes=15)          # a send that never finished (the computer stopped)
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


@contextlib.contextmanager
def _locked(home: Path) -> Iterator[list[dict[str, Any]]]:
    """Read, change and write drops.json under one file lock: the page's planning and the
    owner's Accept or Not now never overwrite each other. Saved only if the block finishes."""
    p = _path(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p.with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rows = all_drops(home)
        yield rows
        _save(home, rows)


def waiting(row: dict[str, Any], now: dt.datetime | None = None) -> bool:
    """Waiting for the owner: proposed, or a failed or interrupted send still inside the
    window where a retry with the same key cannot send it twice."""
    if row["status"] == "PROPOSED":
        return True
    at = row.get("sending_at")
    if row["status"] not in ("FAILED", "SENDING") or not at:
        return False
    age = _now(now) - dt.datetime.fromisoformat(at)
    return age < RETRY_WINDOW and (row["status"] == "FAILED" or age > STUCK)


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
    if found is None:
        return []
    _, prof = found
    prices = prof.get("prices") or {}
    with _locked(home) as rows:
        for kind, (smart, level, key, preview_level) in KINDS.items():
            mine = [r for r in rows if r["kind"] == kind]
            if any(waiting(r, now) for r in mine):
                continue
            last = max((r["created_at"] for r in mine), default="")
            if last and _now(now) - dt.datetime.fromisoformat(last) < EVERY:
                continue
            if not prices.get(key):
                continue                           # the owner's price first (prices card)
            sold = [r for r in rows if r["status"] != "SKIPPED"]  # a skipped drop frees them
            used = {r["locked"] for r in sold} | {r["preview"] for r in sold if r.get("preview")}
            locked = _pick(home, level, used)
            preview = _pick(home, preview_level, used) if preview_level is not None else None
            if locked is None or (preview_level is not None and preview is None):
                continue                           # nothing new to sell this week
            rows.append({"drop_id": "dr_" + secrets.token_hex(5), "kind": kind, "list": smart,
                         "locked": locked["picture"], "level": level,
                         "preview": preview["picture"] if preview else None,
                         "price_cents": int(round(float(prices[key]) * 100)),
                         "text": TEXTS[kind], "status": "PROPOSED",
                         "created_at": _now(now).isoformat()})
        return [dict(r) for r in rows if waiting(r, now)]


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


# What Fanvue's 201 says (send-a-mass-message, read 2026-11-21): no status = sent; SENDING or
# SCHEDULED = accepted, delivery still going on; FAILED, UNSENT or MODERATED = not delivered.
DELIVERING = {"SENDING", "SCHEDULED"}
NOT_SENT = {"FAILED", "UNSENT", "MODERATED"}


def send(home: Path, drop_id: str, client: Any, by: str) -> dict[str, Any]:
    """Only on the owner's Accept. Sent once: a retry reuses the drop's key, and Fanvue replays
    the first send instead of sending again."""
    from .fan_chat import _media_uuid
    from .governor import hold_reason
    if not by.startswith("human:"):
        raise PermissionError("only the owner sends a drop")
    if (why := hold_reason(home)) is not None:
        raise DropError(f"BAU is on HOLD ({why}): nothing is sent until it is released")
    with _locked(home) as rows:
        row = next((r for r in rows if r["drop_id"] == drop_id), None)
        if row is None or not waiting(row):
            raise DropError(f"{drop_id} is not waiting to be sent")
        if bad := problems(home, row):
            raise DropError("; ".join(bad))
        before = row["status"]
        row.update(status="SENDING", sent_by=by,               # never twice
                   sending_at=row.get("sending_at") or _now().isoformat())
        row = dict(row)
    audit = AuditLog(home / "audit" / "chain.jsonl")

    def record(**changes: Any) -> dict[str, Any]:
        with _locked(home) as rows:
            mine = next(r for r in rows if r["drop_id"] == drop_id)
            mine.update(changes)
            return dict(mine)
    try:
        locked = _media_uuid(home, client, row["locked"])
        preview = _media_uuid(home, client, row["preview"]) if row.get("preview") else None
        if (why := hold_reason(home)) is not None:          # set while the pictures uploaded
            record(status=before)
            raise DropError(f"BAU is on HOLD ({why}): nothing is sent until it is released")
        media = [preview, locked] if preview else [locked]
        out = client.mass_message(row["list"], row["text"], media, preview,
                                  row["price_cents"], key=drop_id)
    except DropError:
        raise
    except Exception as e:
        record(status="FAILED", error=str(e)[:300])
        audit.append("fanvue.drop_failed", by, {"drop": drop_id})
        raise
    said = out.get("status")
    if said in NOT_SENT:
        done = record(status="REFUSED" if said == "MODERATED" else "FAILED",
                      error=f"Fanvue said {said}", message_uuid=out.get("uuid"),
                      fanvue_status=said)
        audit.append("fanvue.drop_failed", by, {"drop": drop_id, "fanvue": said})
        raise DropError(f"Fanvue did not send it: {said}")
    done = record(status="DELIVERING" if said in DELIVERING else "SENT",
                  sent_at=_now().isoformat(), message_uuid=out.get("uuid"),
                  recipients=out.get("recipientCount"), fanvue_status=said, error=None)
    audit.append("fanvue.drop_sent", by, {"drop": drop_id, "list": row["list"],
                                          "price_cents": row["price_cents"],
                                          "recipients": out.get("recipientCount"),
                                          "fanvue": said or "SENT"})
    return done


def skip(home: Path, drop_id: str, by: str) -> dict[str, Any]:
    """Not now: this week's drop is skipped; next week's comes with new pictures."""
    if not by.startswith("human:"):
        raise PermissionError("only the owner skips a drop")
    with _locked(home) as rows:
        row = next((r for r in rows if r["drop_id"] == drop_id), None)
        if row is None or not waiting(row):
            raise DropError(f"{drop_id} is not waiting")
        row["status"] = "SKIPPED"
        row = dict(row)
    AuditLog(home / "audit" / "chain.jsonl").append("fanvue.drop_skipped", by,
                                                    {"drop": drop_id})
    return row
