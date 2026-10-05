"""Publishing hub: one place every platform plugs into.

Each platform is an ``Adapter`` with the same four abilities: list what is waiting,
build the card the owner confirms (summary, owner-only choices, preview), post after
the owner confirms, and say whether it accepts child-directed content. Jarvis, the CLI
and Mission Control talk to the hub, so adding a platform (Instagram, Facebook,
Snapchat...) means writing one adapter and registering it in ``ADAPTERS``.

Nothing here posts on its own: ``post`` requires a human approver, and owner-only
choices (privacy, audience, commercial disclosure) come only from the confirmation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .audit import AuditLog
from .home import bau_home


class Adapter:
    name = "base"
    label = "Platform"
    allows_kids = False          # may child-directed (made for kids) videos go here?
    kids_note = ""

    def __init__(self, home: Path, audit: AuditLog, client: Any = None):
        self.home, self.audit, self._client = home, audit, client

    def pending(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def card(self, item_id: str) -> dict[str, Any]:
        """{"summary", "form"?, "preview"?}. Raises ValueError when nothing can be posted."""
        raise NotImplementedError

    def post(self, item_id: str, choices: dict[str, Any], approver: str) -> dict[str, Any]:
        raise NotImplementedError


class TikTokAdapter(Adapter):
    name, label = "tiktok", "TikTok"
    kids_note = ("TikTok is for ages 13 and up, so BAU never posts child-directed videos "
                 "there. Kids videos go to YouTube, marked made for kids.")

    @property
    def queue(self):
        from .tiktok import TikTokQueue
        return TikTokQueue(self.home, self.audit)

    @property
    def client(self):
        from .tiktok import TikTokClient
        return self._client or TikTokClient(self.home)

    def _item(self, item_id: str):
        return next((i for i in self.queue.pending() if i.item_id == item_id), None)

    def pending(self) -> list[dict[str, Any]]:
        return [{"platform": self.name, "item_id": i.item_id, "video": i.video,
                 "title": i.caption, "ai_label": i.is_aigc, "made_for_kids": False,
                 "checks_ok": i.checks.get("ok"), "problems": i.checks.get("problems", [])}
                for i in self.queue.pending()]

    def card(self, item_id: str) -> dict[str, Any]:
        """TikTok's sharing rules: account, preview, caption, AI label; privacy and
        commercial disclosure picked by the owner with no defaults."""
        from .tiktok import (
            BRANDED_CONFIRMATION,
            MUSIC_CONFIRMATION,
            PRIVACY_LABELS,
            TikTokError,
            duration_sec,
        )
        item = self._item(item_id)
        if item is None:
            raise ValueError(f"{item_id} is not waiting in the TikTok queue")
        if not item.checks.get("ok"):
            why = item.checks.get("problems") or [f"compliance gate {item.checks.get('gate')}"]
            raise ValueError("blocked by checks: " + "; ".join(why))
        try:
            creator = self.client.creator_info()
        except (TikTokError, OSError) as e:
            raise ValueError(f"TikTok is not connected ({e}); run: bau tiktok login") from e
        video = self.queue.path(item)
        secs, max_s = duration_sec(video), creator.get("max_video_post_duration_sec")
        if secs is not None and max_s and secs > float(max_s):
            raise ValueError(f"video is longer than this account allows ({max_s}s)")
        acct = f"{creator.get('creator_nickname', '?')} (@{creator.get('creator_username', '?')})"
        summary = (f"Post to TikTok now?\nAccount: {acct}\nCaption: {item.caption}\n"
                   + (f"Length: {secs:.1f}s\n" if secs is not None else "")
                   + f"AI-generated label: {'ON' if item.is_aigc else 'off'}\n"
                   "It can take a few minutes for TikTok to process the video after posting.")
        form = {"fields": [
            {"name": "privacy", "label": "Who can view this video?",
             "options": [[o, PRIVACY_LABELS.get(o, o)]
                         for o in creator.get("privacy_level_options") or []]},
            {"name": "promotes", "label": "Does it promote something?",
             "options": [["none", "No"], ["own_brand", "Yes - your own brand"],
                         ["branded_content", "Yes - branded content for someone else"]]}],
            "notes": {"default": MUSIC_CONFIRMATION, "branded_content": BRANDED_CONFIRMATION}}
        return {"summary": summary, "form": form, "preview": str(video)}

    def post(self, item_id: str, choices: dict[str, Any], approver: str) -> dict[str, Any]:
        privacy, promotes = choices.get("privacy", ""), choices.get("promotes", "")
        if not privacy or promotes not in ("none", "own_brand", "branded_content"):
            return {"error": "the owner must choose who can view it and whether it promotes "
                             "anything"}
        if promotes == "branded_content" and privacy == "SELF_ONLY":
            return {"error": "branded content cannot be 'Only me'"}
        item = self._item(item_id)
        if item is None:
            return {"error": f"{item_id} is not waiting in the queue"}
        creator = self.client.creator_info()
        options = {"brand_organic_toggle": promotes == "own_brand",
                   "brand_content_toggle": promotes == "branded_content"}
        done = self.queue.post(item, self.client, approver, privacy, options, creator)
        return {"platform": self.name, "item_id": done.item_id, "status": done.status,
                "result": done.result, "account": creator.get("creator_username")}


class YouTubeAdapter(Adapter):
    name, label = "youtube", "YouTube"
    allows_kids = True

    @property
    def queue(self):
        from .youtube import YouTubeQueue
        return YouTubeQueue(self.home, self.audit)

    @property
    def client(self):
        from .youtube import YouTubeClient
        return self._client or YouTubeClient(self.home)

    def _item(self, item_id: str):
        return next((i for i in self.queue.pending() if i.item_id == item_id), None)

    def pending(self) -> list[dict[str, Any]]:
        return [{"platform": self.name, "item_id": i.item_id, "video": i.video,
                 "title": i.title, "ai_label": i.is_aigc, "made_for_kids": i.kids,
                 "checks_ok": i.checks.get("ok"), "problems": i.checks.get("problems", []),
                 "warnings": i.checks.get("warnings", [])}
                for i in self.queue.pending()]

    def card(self, item_id: str) -> dict[str, Any]:
        from .youtube import PRIVACY_LABELS, YouTubeError, duration_sec
        item = self._item(item_id)
        if item is None:
            raise ValueError(f"{item_id} is not waiting in the YouTube queue")
        if not item.checks.get("ok"):
            why = item.checks.get("problems") or [f"compliance gate {item.checks.get('gate')}"]
            raise ValueError("blocked by checks: " + "; ".join(why))
        try:
            ch = self.client.channel()
        except (YouTubeError, OSError) as e:
            raise ValueError(f"YouTube is not connected ({e}); run: bau youtube login") from e
        secs = duration_sec(self.queue.path(item))
        summary = (f"Upload to YouTube now?\nChannel: {ch['title']} {ch.get('handle', '')}"
                   .rstrip() + f"\nTitle: {item.title}\n"
                   + (f"Length: {secs:.1f}s\n" if secs is not None else "")
                   + f"AI label: {'ON' if item.is_aigc else 'off'}\n"
                   + ("Audience: MADE FOR KIDS (comments, personalised ads, notifications and "
                      "end screens off)\n" if item.kids else "")
                   + ("Paid promotion: choose Private, then tick 'includes paid promotion' in "
                      "YouTube Studio before making it public.\n" if item.paid_promotion else "")
                   + "".join(f"Note: {w}\n" for w in item.checks.get("warnings", [])))
        privacy = {"name": "privacy", "label": "Who can see it?",
                   "options": [[k, v] for k, v in PRIVACY_LABELS.items()]}
        if item.kids:
            fields = [{"name": "watched", "label": "Did you watch the whole video?",
                       "options": [["yes", "Yes, I watched all of it"]]}, privacy]
        else:
            fields = [{"name": "audience", "label": "Is this video made for kids? "
                       "(you are legally responsible for this answer)",
                       "options": [["no", "No, it's not made for kids"],
                                   ["yes", "Yes, it's made for kids"]]}, privacy]
        return {"summary": summary.rstrip(), "form": {"fields": fields},
                "preview": str(self.queue.path(item))}

    def post(self, item_id: str, choices: dict[str, Any], approver: str) -> dict[str, Any]:
        from .youtube import YouTubeError
        item = self._item(item_id)
        if item is None:
            return {"error": f"{item_id} is not waiting in the queue"}
        mfk = item.kids or choices.get("audience") == "yes"
        try:
            done = self.queue.post(item, self.client, approver, choices.get("privacy", ""),
                                   mfk, choices.get("watched") == "yes")
        except YouTubeError as e:
            return {"error": str(e)}
        return {"platform": self.name, "item_id": done.item_id, "status": done.status,
                "result": done.result}


ADAPTERS: dict[str, type[Adapter]] = {"tiktok": TikTokAdapter, "youtube": YouTubeAdapter}


class Hub:
    def __init__(self, home: Path | None = None, audit: AuditLog | None = None,
                 clients: dict[str, Any] | None = None):
        self.home = home or bau_home()
        self.audit = audit or AuditLog(self.home / "audit" / "chain.jsonl")
        self.clients = clients or {}

    def adapter(self, platform: str) -> Adapter:
        cls = ADAPTERS.get(platform)
        if cls is None:
            raise ValueError(f"unknown platform {platform!r}; known: {sorted(ADAPTERS)}")
        return cls(self.home, self.audit, self.clients.get(platform))

    def pending(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for name in ADAPTERS:
            try:
                out += self.adapter(name).pending()
            except Exception as e:  # one broken queue must not hide the others
                out.append({"platform": name, "error": f"{type(e).__name__}: {e}"[:200]})
        return out

    def queue(self, video: Path, platforms: list[str], by: str, *, title: str,
              description: str = "", tags: list[str] | None = None, kids: bool = False,
              licensed: bool = False, paid_promotion: bool = False, is_aigc: bool | None = None,
              engine: Any = None) -> list[dict[str, Any]]:
        """Fan one finished video out to several platform queues. Kids videos only go
        where the platform accepts child-directed content."""
        out: list[dict[str, Any]] = []
        for name in platforms:
            ad = self.adapter(name)
            if kids and not ad.allows_kids:
                out.append({"platform": name, "skipped": ad.kids_note})
                continue
            if name == "youtube":
                from .youtube import YouTubeQueue
                it = YouTubeQueue(self.home, self.audit).add(
                    video, title, by, description, tags, kids=kids, licensed=licensed,
                    paid_promotion=paid_promotion, is_aigc=is_aigc, engine=engine)
            elif name == "tiktok":
                from .tiktok import TikTokQueue
                caption = title + (f"\n{description}" if description else "")
                it = TikTokQueue(self.home, self.audit).add(video, caption[:2200], by,
                                                            is_aigc=is_aigc, engine=engine)
            else:
                raise ValueError(f"{name}: no queue wiring yet")
            out.append({"platform": name, "item_id": it.item_id, "ok": it.checks.get("ok"),
                        "problems": it.checks.get("problems", []),
                        "warnings": it.checks.get("warnings", [])})
        return out
