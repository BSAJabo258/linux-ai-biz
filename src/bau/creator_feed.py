"""The creator's feed fills itself (the owner's ask, 2026-11-03: "the loop makes money without
me"). While Fanvue autopost is on, the autopilot keeps the Fanvue queue stocked with as many
posts as the owner's number a day: for each it draws a picture on this computer (ComfyUI,
with its age check), has the local model write the caption, and queues it. The queue adds
the AI label and refuses anything about minors; autopost (src/bau/fanvue.py) posts it.

Pictures are safe for work (what `bau creator draw` makes), so the level follows the owner's
audience: subscribers only means level 1, followers and subscribers means level 0. Each
picture's prompt comes from that level's library (data/creator_prompts.yaml: one line from
every section, after the identity lock), and nothing posts until the owner accepts the picture
on its card in Jarvis (the owner's ask, 2026-11-09: "I just need to approve the materials").
"""

from __future__ import annotations

import datetime as dt
import secrets
from pathlib import Path
from typing import Any

import yaml

from . import autopilot as A

# Everyday scenes for a fashion and lifestyle creator; the owner can list his own as
# `themes:` in the creator profile.
THEMES = ("morning coffee by a sunny window", "autumn city walk in a long coat",
          "getting ready for an evening out", "lazy Sunday on the sofa with a book",
          "rooftop at golden hour", "farmers market on a Saturday", "beach boardwalk at sunset",
          "cozy knitwear by the fireplace", "art gallery afternoon", "new outfit try-on")
SHOTS = ("medium", "full body", "close-up portrait")
CAPTION_SYSTEM = ("You write one short social media caption (under 300 characters) in the "
                  "voice of a fictional adult creator. Plain text, at most two emojis, no "
                  "hashtags about age. Never mention anyone young. Only the caption.")


def tiers() -> dict[int, dict[str, Any]]:
    path = Path(__file__).parent / "data" / "creator_prompts.yaml"
    return {int(k): v for k, v in yaml.safe_load(path.read_text())["levels"].items()}


def pick(level: int) -> dict[str, str]:
    """One line from every section of this level's library."""
    return {name: secrets.choice(lines) for name, lines in tiers()[level]["sections"].items()}


def _profile(home: Path) -> tuple[Path, dict[str, Any]] | None:
    found = sorted((home / "creators").glob("*.yaml")) if (home / "creators").is_dir() else []
    return (found[0], yaml.safe_load(found[0].read_text()) or {}) if found else None


def fill(home: Path) -> int:
    """Queue enough draft jobs that tomorrow's posts exist; none while autopost is off."""
    from .fanvue import Queue, autopost_choice
    choice = autopost_choice(home)
    if not choice or not choice.get("on") or _profile(home) is None:
        return 0
    open_drafts = [t for t in A._load(home)["tasks"] if t["kind"] == "draft"
                   and t["detail"].get("job") == "fanvue_post"
                   and t["state"] in ("queued", "running")]
    q = Queue(home)
    need = choice["per_day"] - len(q.pending()) - len(q.review()) - len(open_drafts)
    _, prof = _profile(home)
    levels = [1 if choice["audience"] == "subscribers" else 0]
    if explicit_ready(prof):
        levels += [2, 3]                          # the paid unlocks, in turn with the base level
    made = len(q.items()) + len(open_drafts)
    themes = list(prof.get("themes") or THEMES)
    timely = _timely(home)
    n = 0
    for i in range(max(0, need)):
        level = levels[(made + i) % len(levels)]
        moment = timely.pop(0) if timely else None   # God's Eye: today's sky, first post
        theme = moment["theme"] if moment else secrets.choice(themes)
        detail = {"job": "fanvue_post", "theme": theme, "level": level,
                  "shot": secrets.choice(SHOTS), "parts": pick(level)}
        if moment:
            detail["timely"] = moment["key"]
        if A.add(home, "draft", f"Fanvue post: {theme} ({secrets.token_hex(2)})", detail,
                 source="autopilot (feed)"):
            n += 1
    return n


def _timely(home: Path, day: dt.date | None = None) -> list[dict[str, str]]:
    """Today's God's Eye sky moments not yet used for a post (one post each)."""
    from .spatial import sky_moments
    day = day or dt.datetime.now(dt.UTC).date()
    used = {t["detail"].get("timely") for t in A._load(home)["tasks"]}
    out = []
    for m in sky_moments(day):
        key = f"{m['name']} {day.isoformat()}"
        if key not in used:
            out.append({**m, "key": key})
    return out[:1]


def explicit_ready(prof: dict[str, Any]) -> bool:
    """Levels 2 and 3 only with Chroma installed, the owner's limits and his prices."""
    from .media import comfy
    prices = prof.get("prices") or {}
    return bool(prof.get("explicit_boundaries") and prices.get("nude") and prices.get("xxx")
                and comfy.chroma_ready())


def caption(home: Path, prof: dict[str, Any], theme: str, factory: Any = None) -> str:
    """The boss model (the owner's local model) writes it; without one, a plain line."""
    from . import team
    boss = team.show(home)["boss"]
    if boss:
        from .runtime import provider_for
        provider, _ = (factory or provider_for)(boss, home)
        ask = (f"Creator: {prof.get('name', 'the creator')}, {prof.get('niche', '')}; voice: "
               f"{prof.get('voice', '')}. Today's post: {theme}.")
        text = (provider.complete(CAPTION_SYSTEM, [{"role": "user", "content": ask}], [],
                                  200).text or "").strip().strip('"')
        if text:
            return text[:300]
    return theme[:1].upper() + theme[1:] + "."


def make_post(home: Path, task: dict[str, Any], draw: Any = None,
              factory: Any = None) -> dict[str, Any]:
    """One draft job: draw, caption, queue. The picture's age check runs inside draw."""
    from .fanvue import Queue
    from .media import comfy
    found = _profile(home)
    if found is None:
        return {"ok": False, "evidence": "no creator profile"}
    _, prof = found
    d = task["detail"]
    name = f"{prof.get('id', 'creator')}-{dt.datetime.now(dt.UTC):%Y%m%d-%H%M%S}-" \
           f"{secrets.token_hex(2)}"
    level, parts = int(d["level"]), d.get("parts") or {}
    scene = ", ".join(parts.values()) or d["theme"]
    negative = comfy.NEGATIVE + ", " + tiers()[level]["negative"]
    price = None
    if level >= 2:                               # the owner's limits never leave the picture
        negative += ", " + ", ".join(_limit_words(prof.get("explicit_boundaries") or []))
        price = round(float(prof["prices"]["nude" if level == 2 else "xxx"]) * 100)
    pic = (draw or comfy.draw)(home, comfy.creator_prompt(prof, scene, d["shot"]), name,
                               negative=negative, lane="explicit" if level >= 2 else "sfw")
    from .automaton import running
    auto = running(home)                         # the automaton: no Accept card, it posts
    item = Queue(home).add(pic["file"], caption(home, prof, d["theme"], factory), level,
                           "autopilot", review=not auto, price_cents=price)
    return {"ok": True, "evidence": ("queued for posting" if auto else "waiting for the owner")
            + f": {item['item_id']} ({pic['file']})"}


def _limit_words(limits: list[str]) -> list[str]:
    """'No animals' -> 'animals': what a limit forbids, for the negative prompt."""
    out = []
    for line in limits:
        t = str(line).strip()
        low = t.lower()
        if low.startswith("no "):
            out.append(t[3:].strip())
    return out
