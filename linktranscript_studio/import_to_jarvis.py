"""Import a transcript collection into Jarvis's searchable local memory.

Each source becomes a separate unverified memory record, preserving its URL and
the ASR text. Re-running the importer updates no existing records and skips
sources already present in MemoryLane.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from bau.brain import Brain
from bau.memory import MemoryLane

HEADING = re.compile(r"(?m)^#{2,3} (.+?)\s*$")
SOURCE = re.compile(r"(?m)^\*\*Source:\*\*\s*\[([^]]*)\]\((https?://[^)]+)\)")
PAGE_TITLE = re.compile(r"(?m)^\*\*Page title:\*\*\s*(.+?)\s*$")
METHOD = re.compile(r"(?m)^\*\*Method:\*\*\s*(.+?)\s*$")
FENCED_TEXT = re.compile(r"```(?:text)?\s*\n(.*?)\n```", re.S)


def transcript_records(markdown: str) -> list[dict[str, str]]:
    """Read source sections from the collection, skipping grouping headings."""
    headings = list(HEADING.finditer(markdown))
    records: list[dict[str, str]] = []
    seen: set[str] = set()
    for i, heading in enumerate(headings):
        start = heading.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(markdown)
        section = markdown[start:end].strip()
        source_match = SOURCE.search(section)
        if not source_match:
            continue
        source_label, source = source_match.groups()
        if source in seen:
            continue
        seen.add(source)

        page_title = PAGE_TITLE.search(section)
        method = METHOD.search(section)
        transcript = FENCED_TEXT.search(section)
        body_parts = [f"Source URL: {source}", f"Video title/description: {source_label}"]
        if page_title:
            body_parts.append(f"Platform title/description: {page_title.group(1).strip()}")
        if method:
            body_parts.append(f"Transcription method: {method.group(1).strip()}")
        body_parts.append("Transcript (automatic speech recognition; unverified):")
        if transcript:
            body_parts.append(transcript.group(1).strip())
        else:
            remaining = section[source_match.end():].strip()
            body_parts.append(remaining or "No transcript text was available.")

        platform = "facebook" if "facebook.com/" in source else (
            "tiktok" if "tiktok.com/" in source else "video")
        records.append({
            "source": source,
            "title": (f"{heading.group(1).strip()} — {source_label}" if platform == "tiktok"
                      else heading.group(1).strip())[:120],
            "body": "\n\n".join(body_parts),
            "platform": platform,
        })
    return records


def import_collection(path: Path, memory: MemoryLane) -> dict[str, int]:
    markdown = path.read_text(encoding="utf-8")
    records = transcript_records(markdown)
    known_sources = {r.source for r in memory._all() if r.kind == "video_transcript"}
    added = 0
    skipped = 0
    for item in records:
        if item["source"] in known_sources:
            skipped += 1
            continue
        memory.add(
            "video_transcript",
            item["title"],
            item["body"],
            tags=["video-transcript", "unverified-asr", item["platform"]],
            status="UNKNOWN",
            source=item["source"],
        )
        known_sources.add(item["source"])
        added += 1
    return {"found": len(records), "added": added, "already_present": skipped}


def import_research_note(path: Path) -> str:
    """Keep the curated, explicitly unverified synthesis in Jarvis's Second Brain."""
    title = "Transcript Collection Research for Jarvis"
    brain = Brain()
    note = brain.upsert(
        title,
        type_="concept",
        source="research",
        data_class="INTERNAL",
        body=path.read_text(encoding="utf-8"),
    )
    note.status = "EXPERIMENTAL"
    brain.save(note)
    return note.id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "collection",
        nargs="?",
        type=Path,
        default=Path(__file__).with_name("transcripts.md"),
        help="Markdown transcript collection (defaults to sibling transcripts.md)",
    )
    args = parser.parse_args()
    if not args.collection.is_file():
        parser.error(f"transcript collection not found: {args.collection}")
    result = import_collection(args.collection, MemoryLane())
    research_path = args.collection.with_name("jarvis_research.md")
    if research_path.is_file():
        result["second_brain_note"] = import_research_note(research_path)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
