"""Series engine: the same characters, looking the same, in every clip of every episode.

The owner fills in a character sheet per main character (``_shared/characters/*.yaml``)
and one style sheet (``_shared/style.yaml``) in a kids workspace. From then on:

- ``lock(id)`` is the one sentence that describes a character; every clip prompt carries it
  word for word, so a video model draws the same character each time;
- ``prompt(scene, cast)`` = style + the cast's locks + the scene + what to avoid;
- ``drift(text)`` finds a character described differently (a colour or a "never" trait not
  on their sheet) or named without their lock;
- ``plan(ep, format)`` scales a story shape (``data/series_formats.yaml``) to the episode's
  length in clip-sized scenes (3-15 s, what the studio's video model takes) and warns when
  the channel starts repeating itself: YouTube demonetises mass-produced, template-driven
  channels (see ``kids.py``), so consistency means the same characters, never the same
  episode.

Nothing here makes or posts a clip: prompts go to the studio, which prices them and makes
them only on the owner's Confirm.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from pathlib import Path
from typing import Any

import yaml

from . import kids
from .home import shipped_data

FIELDS = ("id", "name", "kind", "look", "outfit", "colors", "personality", "voice",
          "catchphrase", "never")
STYLE_FIELDS = ("art_style", "palette", "lighting", "camera", "aspect_ratio", "avoid")
ASPECTS = ("16:9", "9:16", "1:1")
MAX_PROMPT = 2500
CLIP_MIN, CLIP_MAX = 3, 15
COLOURS = {"red", "orange", "yellow", "green", "blue", "purple", "pink", "brown", "black",
           "white", "grey", "gray", "gold", "golden", "silver", "cream", "beige", "teal",
           "violet", "navy", "turquoise", "peach", "mint", "lilac"}
ID = re.compile(r"^[a-z][a-z0-9-]{0,30}$")


class SeriesError(ValueError):
    """The sheets aren't ready, or a prompt can't be made safely."""


def _placeholder(value: Any) -> bool:
    return "{{" in yaml.safe_dump(value)


class Series:
    def __init__(self, ws: Path):
        self.ws = ws
        shared = ws / "_shared"
        self.chars: dict[str, dict[str, Any]] = {}
        self._files: list[tuple[Path, Any]] = []
        for f in sorted((shared / "characters").glob("*.yaml")):
            data = yaml.safe_load(f.read_text()) or {}
            self._files.append((f, data))
            if isinstance(data, dict) and data.get("id"):
                self.chars[str(data["id"])] = data
        try:
            self.style: dict[str, Any] = yaml.safe_load((shared / "style.yaml").read_text()) or {}
        except OSError:
            self.style = {}

    # ---------------------------------------------------------------- the owner's sheets
    def problems(self) -> list[str]:
        out = []
        if not self._files:
            out.append("no characters yet: add a sheet to _shared/characters/")
        for f, c in self._files:
            if not isinstance(c, dict):
                out.append(f"{f.name}: not a character sheet")
                continue
            if _placeholder(c):
                out.append(f"{f.name}: fill in every {{{{...}}}} first")
                continue
            missing = [k for k in FIELDS if not c.get(k)]
            if missing:
                out.append(f"{f.name}: missing {', '.join(missing)}")
                continue
            if not ID.match(str(c["id"])):
                out.append(f"{f.name}: id must be short and lowercase, like 'pip'")
            if not isinstance(c["look"], list) or len(c["look"]) < 3:
                out.append(f"{f.name}: 'look' needs at least three things to recognise "
                           f"{c['name']} by")
            if kids.FRANCHISE.search(f"{c['name']} {c['kind']}"):
                out.append(f"{f.name}: {c['name']} looks like another company's character")
        if _placeholder(self.style):
            out.append("style.yaml: fill in every {{...}} first")
        else:
            missing = [k for k in STYLE_FIELDS if not self.style.get(k)]
            if missing:
                out.append(f"style.yaml: missing {', '.join(missing)}")
            elif self.style["aspect_ratio"] not in ASPECTS:
                out.append(f"style.yaml: aspect_ratio must be one of {', '.join(ASPECTS)}")
        return out

    def _ready(self) -> None:
        probs = self.problems()
        if probs:
            raise SeriesError("the series sheets aren't ready: " + "; ".join(probs))

    # ---------------------------------------------------------------- the lock
    def lock(self, cid: str) -> str:
        c = self.chars.get(cid)
        if c is None:
            raise SeriesError(f"no character {cid!r}; have {', '.join(self.chars) or 'none'}")
        return f"{c['name']} is {c['kind']}: {'; '.join(c['look'])}; wearing {c['outfit']}."

    def prompt(self, scene: str, cast: list[str]) -> str:
        self._ready()
        scene = " ".join(scene.split())
        if not scene:
            raise SeriesError("describe the scene")
        bad = [i for i in kids.scan("", scene) if i["issue"] != "clickbait"]
        if bad:
            raise SeriesError("not for kids: " + "; ".join(i["detail"] for i in bad))
        locks = " ".join(self.lock(c) for c in cast)
        st = self.style
        text = (f"{st['art_style']}. {st['palette']}. {st['lighting']}. "
                f"Camera: {st['camera']}.\nCharacters: {locks}\nScene: {scene}\n"
                f"Avoid: {', '.join(st['avoid'])}.")
        if len(text) > MAX_PROMPT:
            raise SeriesError(f"prompt is {len(text)} characters; the video model takes "
                              f"{MAX_PROMPT}: shorten the scene or the sheets")
        return text

    # ---------------------------------------------------------------- drift
    def drift(self, text: str) -> list[dict[str, str]]:
        """Characters described off their sheet, or named without their lock. Checked per
        item: a numbered entry or a paragraph (one clip prompt spans several lines)."""
        issues = []
        locks = {cid: self.lock(cid) for cid in self.chars}
        style = [str(v) for k, v in self.style.items() if k in STYLE_FIELDS and k != "avoid"]
        style.append(", ".join(self.style.get("avoid") or []))
        items = [t for t in re.split(r"\n\s*\n|\n(?=\s*\d+[.)]\s)", text) if t.strip()]
        for n, item in enumerate(items, 1):
            bare = item
            for chunk in [*locks.values(), *style]:
                if chunk:
                    bare = bare.replace(chunk, " ")
            for cid, c in self.chars.items():
                name = re.compile(rf"\b{re.escape(c['name'])}\b")
                if not name.search(item):
                    continue
                if locks[cid] not in item:
                    issues.append({"issue": "no_lock", "detail": f"item {n}: {c['name']} "
                                   "is named without their character description"})
                own = {w.lower() for w in c["colors"]}
                for m in name.finditer(bare):
                    near = re.findall(r"[a-z]+", bare[m.end():m.end() + 60].lower())[:8]
                    for w in near:
                        if w in COLOURS and w not in own:
                            issues.append({"issue": "off_model", "detail":
                                           f"item {n}: {c['name']} is shown {w}; their "
                                           f"sheet says {', '.join(c['colors'])}"})
                    for trait in c["never"]:
                        if trait.lower() in " ".join(near):
                            issues.append({"issue": "off_model", "detail":
                                           f"item {n}: {c['name']} is never {trait}"})
        return issues

    # ---------------------------------------------------------------- formats and plans
    def formats(self) -> dict[str, dict[str, Any]]:
        own = self.ws / "_shared" / "formats.yaml"
        base = yaml.safe_load((shipped_data() / "series_formats.yaml").read_text())
        if own.is_file():
            base.update(yaml.safe_load(own.read_text()) or {})
        return base

    def plan(self, ep: Path, fmt: str, seconds: int = 60,
             cast: list[str] | None = None) -> dict[str, Any]:
        self._ready()
        formats = self.formats()
        if fmt not in formats:
            raise SeriesError(f"no format {fmt!r}; have {', '.join(formats)}")
        if not 10 <= seconds <= 600:
            raise SeriesError("an episode is 10 to 600 seconds")
        cast = list(cast or sorted(self.chars, key=lambda c: (
            self.chars[c].get("role") != "main", c)))     # the main character leads
        for cid in cast:
            self.lock(cid)                                  # unknown ids fail here
        idea = _idea(ep)
        lead = self.chars[cast[0]]["name"]
        friend = self.chars[cast[1]]["name"] if len(cast) > 1 else lead
        scenes = []
        for beat in formats[fmt]["beats"]:
            length = beat["share"] * seconds
            parts = max(1, math.ceil(length / CLIP_MAX))
            for k in range(1, parts + 1):
                scene = beat["goal"].format(lead=lead, friend=friend, idea=idea)
                if parts > 1:
                    scene += f" (Part {k} of {parts}: carry on from the last clip.)"
                scenes.append({"beat": beat["name"], "raw": length / parts, "scene": scene})
        _fit(scenes, seconds)
        for i, sc in enumerate(scenes, 1):
            # Only the characters in the scene are described: shorter, clearer prompts.
            here = [c for c in cast if re.search(rf"\b{re.escape(self.chars[c]['name'])}\b",
                                                 sc["scene"])] or cast[:1]
            sc.update(n=i, cast=here, prompt=self.prompt(sc["scene"], here))
            sc.pop("raw")
        warnings = self._sameness(ep, fmt, idea)
        record = {"format": fmt, "cast": cast, "seconds": seconds,
                  "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}
        (ep / "series.yaml").write_text(yaml.safe_dump(record, sort_keys=False))
        (ep / "series-plan.md").write_text(_markdown(idea, fmt, seconds, scenes, warnings))
        return {"episode": ep.name, "idea": idea, "format": fmt, "seconds": seconds,
                "cast": cast, "scenes": scenes, "warnings": warnings,
                "next": "price a scene: bau video quote \"<prompt>\" --duration <seconds>"}

    def _sameness(self, ep: Path, fmt: str, idea: str) -> list[str]:
        from .workspace import episodes
        earlier = [p for p in episodes(self.ws) if p != ep and p.name < ep.name]
        used = [(yaml.safe_load((p / "series.yaml").read_text()) or {}).get("format")
                for p in earlier if (p / "series.yaml").is_file()]
        out = []
        if len(used) >= 3 and all(u == fmt for u in used[-3:]):
            out.append(f"the same format ({fmt}) for the fourth episode in a row: mix it up, "
                       "or the channel looks mass-produced (YouTube demonetises that)")
        dup = kids.near_duplicate(idea, [(p.name, _idea(p)) for p in earlier], threshold=.5)
        if dup:
            out.append(f"this idea is almost the same as {dup}: give it its own twist")
        return out


def _idea(ep: Path) -> str:
    try:
        first = (ep / "brief.md").read_text().splitlines()[0]
    except (OSError, IndexError):
        return ep.name
    return first.lstrip("# ").strip() or ep.name


def _fit(scenes: list[dict[str, Any]], seconds: int) -> None:
    """Whole seconds, each clip 3-15 s, adding up to the episode length where possible."""
    for sc in scenes:
        sc["seconds"] = min(CLIP_MAX, max(CLIP_MIN, round(sc["raw"])))
    gap = seconds - sum(sc["seconds"] for sc in scenes)
    for sc in sorted(scenes, key=lambda s: -s["raw"]):
        if not gap:
            break
        step = max(-(sc["seconds"] - CLIP_MIN), min(CLIP_MAX - sc["seconds"], gap))
        sc["seconds"] += step
        gap -= step


def _markdown(idea: str, fmt: str, seconds: int, scenes: list[dict[str, Any]],
              warnings: list[str]) -> str:
    lines = [f"# Series plan: {idea}", "", f"Format: {fmt}, about {seconds} s, "
             f"{len(scenes)} clips. Starting prompts: the storyboard and video-prompt "
             "stages refine them; the character descriptions stay word for word.", ""]
    lines += [f"> Warning: {w}" for w in warnings] + ([""] if warnings else [])
    for sc in scenes:
        lines += [f"## {sc['n']}. {sc['beat']} ({sc['seconds']} s)", "", sc["scene"], "",
                  "```text", sc["prompt"], "```", ""]
    return "\n".join(lines)
