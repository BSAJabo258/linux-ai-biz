"""Results tracker: what each posted video did, and whether it made money.

For every video BAU posted (the YouTube and TikTok queues), ``refresh`` reads the numbers
back: views, watch time, likes, subscribers and, on YouTube, estimated earnings. ``link``
ties a video to the studio clips it used and to its episode, so ``report`` can show the
cost of each video next to what it earned, and which story formats people watch longest.

Read only: the tracker never posts, edits or deletes anything on a platform. Platform
facts (endpoints, scopes, limits) are in the docstrings of ``youtube.py`` and
``tiktok.py``. Earnings are YouTube's estimates (adjusted at month end), never a promise;
the money actually paid out is recorded in the ledger as before.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import yaml

from .audit import AuditLog
from .economics import Ledger
from .home import bau_home
from .store import JsonlStore

POLITE = dt.timedelta(hours=1)      # one refresh an hour per platform is plenty
YT_METRICS = ("views", "estimatedMinutesWatched", "averageViewDuration",
              "averageViewPercentage", "subscribersGained", "likes", "comments", "shares")
YT_FIELDS = {"views": "views", "estimatedMinutesWatched": "watch_minutes",
             "averageViewDuration": "avg_view_seconds", "averageViewPercentage": "avg_view_pct",
             "subscribersGained": "subscribers_gained", "likes": "likes",
             "comments": "comments", "shares": "shares"}
TT_FIELDS = {"view_count": "views", "like_count": "likes", "comment_count": "comments",
             "share_count": "shares"}
NO_EARNINGS_YT = ("YouTube didn't share earnings: the channel may not be in the YouTube "
                  "Partner Program yet, or revenue wasn't allowed at `bau youtube login`")
NO_EARNINGS_TT = ("TikTok doesn't report earnings through its API: check the TikTok app "
                  "and record payouts in the ledger")
NOT_LINKED = ("cost unknown: tell BAU which clips it used with "
              "`bau results link <platform> <item> --clips ...`")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _batches(items: list[str], n: int) -> list[list[str]]:
    return [items[i:i + n] for i in range(0, len(items), n)]


class Results:
    def __init__(self, home: Path | None = None, audit: AuditLog | None = None,
                 clients: dict[str, Any] | None = None):
        self.home = home or bau_home()
        self.audit = audit or AuditLog(self.home / "audit" / "chain.jsonl")
        self.clients = clients or {}
        self.snaps = JsonlStore(self.home / "results" / "snapshots.jsonl")
        self.links = JsonlStore(self.home / "results" / "links.jsonl")

    # ---------------------------------------------------------------- what was posted
    def videos(self) -> list[dict[str, Any]]:
        from .tiktok import TikTokQueue
        from .youtube import YouTubeQueue
        out = []
        for i in YouTubeQueue(self.home, self.audit).items():
            if i.status == "POSTED" and i.video_id:
                out.append({"platform": "youtube", "item_id": i.item_id,
                            "video_id": i.video_id, "title": i.title,
                            "posted_at": i.result.get("at", ""), "made_for_kids": i.kids})
        for i in TikTokQueue(self.home, self.audit).items():
            post = i.result.get("publicaly_available_post_id")   # TikTok's own spelling
            post = post[0] if isinstance(post, list) and post else post
            if i.status == "POSTED" and post:
                out.append({"platform": "tiktok", "item_id": i.item_id, "video_id": str(post),
                            "title": i.caption, "posted_at": i.created_at,
                            "made_for_kids": False})
        return out

    # ---------------------------------------------------------------- linking costs
    def link(self, platform: str, item_id: str, by: str, clips: list[str] | None = None,
             episode: str = "") -> dict[str, Any]:
        """Tie a posted video to the studio clips it used and its episode
        (``workspace/ep-001``). Bookkeeping only: nothing is sent anywhere."""
        if not any(v["platform"] == platform and v["item_id"] == item_id
                   for v in self.videos()):
            raise ValueError(f"no posted {platform} video {item_id!r}")
        known = {j["id"] for j in JsonlStore(self.home / "studio" / "jobs.jsonl")}
        unknown = [c for c in clips or [] if c not in known]
        if unknown:
            raise ValueError(f"no studio clip {', '.join(unknown)} (see `bau video clips`)")
        if episode:
            from . import workspace as W
            ws, _, ep = episode.partition("/")
            try:
                episode = f"{ws}/{W.find_episode(W.root(self.home) / ws, ep).name}"
            except W.WorkspaceError as e:
                raise ValueError(f"{e} - write it as workspace/episode, "
                                 "e.g. kids-channel/ep-001") from e
        rec = {"platform": platform, "item_id": item_id, "clips": list(clips or []),
               "episode": episode, "by": by, "at": _now().isoformat(timespec="seconds")}
        self.links.append(rec)
        self.audit.append("results.linked", by, {"platform": platform, "item_id": item_id,
                                                 "clips": len(rec["clips"])})
        return rec

    def _links(self) -> dict[tuple[str, str], dict[str, Any]]:
        return {(r["platform"], r["item_id"]): r for r in self.links}

    # ---------------------------------------------------------------- reading the numbers
    def _client(self, platform: str) -> Any:
        if platform in self.clients:
            return self.clients[platform]
        if platform == "youtube":
            from .youtube import YouTubeClient
            return YouTubeClient(self.home)
        from .tiktok import TikTokClient
        return TikTokClient(self.home)

    def _last(self, platform: str) -> dt.datetime | None:
        ats = [r["at"] for r in self.snaps if r["platform"] == platform]
        return dt.datetime.fromisoformat(max(ats)) if ats else None

    def refresh(self, force: bool = False, by: str = "results") -> dict[str, Any]:
        out: dict[str, Any] = {"refreshed": {}, "skipped": {}, "errors": {}}
        vids = self.videos()
        for platform, fetch in (("youtube", self._youtube), ("tiktok", self._tiktok)):
            mine = [v for v in vids if v["platform"] == platform]
            if not mine:
                continue
            last = self._last(platform)
            if not force and last and _now() - last < POLITE:
                out["skipped"][platform] = f"read at {last:%H:%M} UTC; again after an hour"
                continue
            try:
                rows = fetch(mine)
            except Exception as e:  # one platform down never stops the other
                out["errors"][platform] = str(e)[:300]
                continue
            at = _now().isoformat(timespec="seconds")
            for r in rows:
                self.snaps.append({"at": at, "platform": platform, **r})
            out["refreshed"][platform] = len(rows)
        self.audit.append("results.refreshed", by, {**out["refreshed"],
                                                    "errors": sorted(out["errors"])})
        return out

    def _youtube(self, vids: list[dict[str, Any]]) -> list[dict[str, Any]]:
        from .youtube import YouTubeError
        c = self._client("youtube")
        if not c.granted("https://www.googleapis.com/auth/yt-analytics.readonly"):
            raise YouTubeError("BAU now also reads your channel's numbers: run "
                               "`bau youtube login` once more and allow it")
        start = min((v["posted_at"][:10] for v in vids if v["posted_at"]),
                    default=(_now() - dt.timedelta(days=90)).date().isoformat())
        base = {"ids": "channel==MINE", "startDate": start,
                "endDate": _now().date().isoformat(), "dimensions": "video",
                "sort": "-views", "maxResults": "200"}
        rows: dict[str, dict[str, Any]] = {}
        for ids in _batches([v["video_id"] for v in vids], 200):
            q = {**base, "filters": "video==" + ",".join(ids)}
            for row in _table(c.analytics({**q, "metrics": ",".join(YT_METRICS)})):
                rows[row["video"]] = {YT_FIELDS[k]: v for k, v in row.items() if k in YT_FIELDS}
            try:
                money = _table(c.analytics({**q, "metrics": "estimatedRevenue"}))
            except YouTubeError:
                money = None
            for vid in ids:
                r = rows.setdefault(vid, {})          # no rows yet = no views yet
                if money is None:
                    r.update(revenue_usd=None, note=NO_EARNINGS_YT)
                else:
                    got = {m["video"]: m["estimatedRevenue"] for m in money}
                    r["revenue_usd"] = round(float(got.get(vid, 0.0)), 2)
        return [{"video_id": vid, **r} for vid, r in rows.items()]

    def _tiktok(self, vids: list[dict[str, Any]]) -> list[dict[str, Any]]:
        from .tiktok import TikTokError
        c = self._client("tiktok")
        if not c.granted("video.list"):
            raise TikTokError("BAU now also reads your video counts: run `bau tiktok login` "
                              "once more and allow it")
        out = []
        for ids in _batches([v["video_id"] for v in vids], 20):
            for v in c.videos(ids):
                out.append({"video_id": str(v.get("id")), "revenue_usd": None,
                            "note": NO_EARNINGS_TT,
                            **{TT_FIELDS[k]: v.get(k) for k in TT_FIELDS}})
        return out

    # ---------------------------------------------------------------- the report
    def report(self) -> dict[str, Any]:
        latest: dict[tuple[str, str], dict[str, Any]] = {}
        for r in self.snaps:
            latest[(r["platform"], r["video_id"])] = r
        links = self._links()
        led = Ledger(self.home)
        cost_of = {}
        for c in led.costs:
            if c.get("job_id"):
                cost_of[c["job_id"]] = cost_of.get(c["job_id"], 0.0) + c["usd"]
        used: set[str] = set()
        rows = []
        for v in self.videos():
            snap = latest.get((v["platform"], v["video_id"]), {})
            link = links.get((v["platform"], v["item_id"]), {})
            notes = [snap["note"]] if snap.get("note") else []
            if not snap:
                notes.append("no numbers yet: run `bau results refresh`")
            cost = None
            if link.get("clips"):
                used.update(link["clips"])
                cost = round(sum(cost_of.get(c, 0.0) for c in link["clips"]), 2)
            else:
                notes.append(NOT_LINKED)
            rev = snap.get("revenue_usd")
            row = {**v, **{k: snap.get(k) for k in ("views", "watch_minutes", "avg_view_pct",
                                                     "avg_view_seconds", "likes", "comments",
                                                     "shares", "subscribers_gained")},
                   "revenue_usd": rev, "cost_usd": cost,
                   "profit_usd": round(rev - cost, 2) if rev is not None and cost is not None
                   else None,
                   "episode": link.get("episode", ""), "format": self._format(link),
                   "checked_at": snap.get("at", ""), "notes": notes}
            rows.append(row)
        rows.sort(key=lambda r: -(r["views"] or 0))
        known_rev = [r["revenue_usd"] for r in rows if r["revenue_usd"] is not None]
        known_cost = [r["cost_usd"] for r in rows if r["cost_usd"] is not None]
        unlinked = round(sum(v for k, v in cost_of.items()
                             if k.startswith("clip_") and k not in used), 2)
        totals = {"videos": len(rows), "views": sum(r["views"] or 0 for r in rows),
                  "revenue_usd": round(sum(known_rev), 2) if known_rev else None,
                  "cost_usd": round(sum(known_cost), 2),
                  "unlinked_clip_spend_usd": unlinked}
        by_format = _by_format(rows)
        notes = ["Earnings are YouTube's estimates and change at month end; what is "
                 "actually paid out goes in the ledger."]
        if not rows:
            notes.insert(0, "Nothing posted yet: post a video from the publish queue, then "
                            "run `bau results refresh` a day or so later.")
        if unlinked:
            notes.append(f"${unlinked:.2f} of clips aren't linked to a posted video yet.")
        return {"videos": rows, "totals": totals, "by_format": by_format,
                "best": [{k: r[k] for k in ("platform", "video_id", "title", "views")}
                         for r in rows[:3] if r["views"]],
                "what_works": [f"{f['format']}: {f['avg_views']:,} views a video "
                               f"({f['videos']} video(s))" +
                               (f", watched {round(f['avg_view_pct'])}% through"
                                if f["avg_view_pct"] is not None else "")
                               for f in by_format],
                "notes": notes}

    def _format(self, link: dict[str, Any]) -> str:
        if not link.get("episode"):
            return ""
        from . import workspace as W
        f = W.root(self.home) / link["episode"].split("/")[0] / "episodes" / \
            link["episode"].split("/", 1)[1] / "series.yaml"
        try:
            return (yaml.safe_load(f.read_text()) or {}).get("format", "")
        except OSError:
            return ""


def _table(data: dict[str, Any]) -> list[dict[str, Any]]:
    names = [h["name"] for h in data.get("columnHeaders") or []]
    return [dict(zip(names, row, strict=False)) for row in data.get("rows") or []]


def _by_format(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        if r["format"] and r["views"] is not None:
            groups.setdefault(r["format"], []).append(r)
    out = []
    for fmt, rs in groups.items():
        pct = [r["avg_view_pct"] for r in rs if r["avg_view_pct"] is not None]
        rev = [r["revenue_usd"] for r in rs if r["revenue_usd"] is not None]
        out.append({"format": fmt, "videos": len(rs),
                    "avg_views": round(sum(r["views"] for r in rs) / len(rs)),
                    "avg_view_pct": round(sum(pct) / len(pct), 1) if pct else None,
                    "revenue_usd": round(sum(rev), 2) if rev else None})
    return sorted(out, key=lambda f: -f["avg_views"])
