"""Fetch Social Crawl TikTok profile pages and append local Whisper transcripts."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import app

BASE = "https://www.socialcrawl.dev/v1/tiktok/profile/videos"
OUT = Path(__file__).with_name("transcripts.md")
STATE = Path(__file__).with_name("tiktok_profile_cursor.json")


def fetch(handle: str, key: str, cursor: str | None) -> dict:
    params = {"handle": handle}
    if cursor:
        params["cursor"] = cursor
    request = urllib.request.Request(
        BASE + "?" + urllib.parse.urlencode(params),
        headers={"x-api-key": key, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def existing_ids() -> set[str]:
    if not OUT.exists():
        return set()
    return {line.strip().rsplit("/", 1)[-1].rstrip(")")
            for line in OUT.read_text().splitlines()
            if "tiktok.com/@" in line and "/video/" in line}


def append_item(post: dict, handle: str) -> None:
    url = post.get("url") or ""
    title = post.get("content", {}).get("text") or f"TikTok video {post.get('id', '')}"
    published = (post.get("published_at") or "")[:10]
    duration = post.get("content", {}).get("duration_seconds")
    try:
        if duration and float(duration) > 300:
            raise RuntimeError("Skipped: video is longer than the 5-minute batch limit")
        transcript = app.transcribe_url(url).get("text", "").strip()
        error = ""
    except Exception as exc:  # preserve failures in the batch report
        transcript, error = "", str(exc)
    with OUT.open("a", encoding="utf-8") as stream:
        stream.write(f"\n### {published or 'Date unavailable'} — {duration or '?'} seconds\n\n")
        stream.write(f"**Source:** [{title}]({url})\n\n")
        if error:
            stream.write(f"Transcription failed: {error}\n")
        elif transcript:
            stream.write("```text\n" + transcript + "\n```\n")
        else:
            stream.write("No intelligible speech detected.\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handle", default="charlidamelio")
    parser.add_argument("--pages", type=int, default=10,
                        help="maximum pages to fetch in this run (10 videos per page currently)")
    parser.add_argument("--resume", action="store_true", help="continue using the saved cursor")
    args = parser.parse_args()
    key = os.environ.get("SOCIALCRAWL_API_KEY") or getpass.getpass("Social Crawl API key: ")
    state = json.loads(STATE.read_text()) if args.resume and STATE.exists() else {}
    cursor = state.get("cursor")
    seen = existing_ids()
    spent = 0
    for page_no in range(1, args.pages + 1):
        payload = fetch(args.handle, key, cursor)
        if not payload.get("success"):
            print(f"API error: {payload.get('error') or payload}", file=sys.stderr, flush=True)
            return 1
        data = payload.get("data") or {}
        items = data.get("items") or []
        print(f"Page {page_no}/{args.pages}: {len(items)} videos; "
              f"{payload.get('credits_used', 0)} API credit(s)", flush=True)
        spent += int(payload.get("credits_used", 0))
        for index, row in enumerate(items, 1):
            post = row.get("post") or {}
            url = post.get("url") or ""
            vid = url.rsplit("/", 1)[-1]
            if not url or vid in seen:
                continue
            print(f"  Transcribing {index}/{len(items)}: {url}", flush=True)
            append_item(post, args.handle)
            seen.add(vid)
        pagination = payload.get("pagination") or {}
        cursor = pagination.get("next_cursor")
        STATE.write_text(json.dumps({
            "handle": args.handle,
            "cursor": cursor,
            "pages_done": state.get("pages_done", 0) + page_no,
            "credits_remaining": payload.get("credits_remaining"),
        }, indent=2))
        if not pagination.get("has_more") or not cursor:
            print("No more profile videos are available.", flush=True)
            break
    print(f"Finished. This run used {spent} Social Crawl credit(s). Output: {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
