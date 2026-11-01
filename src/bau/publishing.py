"""Publishing hub: one place every platform plugs into.

Each platform is an ``Adapter`` with the same four abilities: list what is waiting,
build the card the owner confirms (summary, owner-only choices, preview), post after
the owner confirms. Jarvis, the CLI
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
                 "title": i.caption, "ai_label": i.is_aigc,
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


ADAPTERS: dict[str, type[Adapter]] = {"tiktok": TikTokAdapter}


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
              description: str = "", is_aigc: bool | None = None,
              engine: Any = None) -> list[dict[str, Any]]:
        """Fan one finished video out to several platform queues."""
        out: list[dict[str, Any]] = []
        for name in platforms:
            self.adapter(name)                       # unknown platform: a plain error
            if name == "tiktok":
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
