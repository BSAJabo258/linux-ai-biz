"""Kids content: what BAU checks before anything child-directed is published.

Children's videos are one of the strongest niches on YouTube, and the most regulated:
COPPA and the 2019 FTC/YouTube settlement make the creator legally responsible for
marking child-directed videos "made for kids", which turns off comments, personalised
ads, notifications and end screens. YouTube also demonetises mass-produced,
template-driven AI channels ("inauthentic content", July 2025).

This module reads a video's title, description and tags and turns them into facts the
``publish`` policy domain (``data/policies/kids_content.yaml``) decides on. It cannot see
the video itself - that is why the owner must confirm they watched the whole thing
before a made-for-kids video goes out.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

_I = re.IGNORECASE

# Asking a child for anything that identifies them, or sending them off-platform.
PERSONAL_INFO = re.compile(
    r"\b(?:tell|send|write|comment|share)\b[^.!?\n]{0,30}\b(?:your|ur)\s+"
    r"(?:name|address|age|school|phone|number|email|birthday|photo|picture|pic|city)\b"
    r"|\bwhat(?:'?s| is) your (?:name|address|school|phone|email)\b"
    r"|\bsend (?:us|me) (?:a )?(?:photo|picture|pic|selfie|video)\b", _I)
LINK = re.compile(r"https?://|\bwww\.|\b[\w-]+\.(?:com|net|org|io|app|ly|gg)\b", _I)
ENGAGEMENT = re.compile(
    r"\b(?:like and subscribe|smash (?:the |that )?(?:like|subscribe)|hit (?:the |that )?"
    r"(?:like|subscribe|bell)|comment below|leave a comment|turn on (?:the )?notifications"
    r"|ring the bell)\b", _I)
PURCHASE = re.compile(
    r"\b(?:buy|order|purchase|get) (?:it |one |yours )?(?:now|today)\b"
    r"|\bask (?:your|ur) (?:mom|mum|dad|parents?|grown[- ]?ups?) to (?:buy|get|order)\b"
    r"|\blimited time\b|\bin[- ]app purchases?\b|\bdownload (?:our|the|my) app\b"
    r"|\bonly \$\d", _I)
UNSUITABLE = re.compile(
    r"\b(?:horror|creepy|gore|gory|blood(?:y)?|kill(?:s|ed|ing|er)?|murder\w*|guns?|knife|"
    r"knives|weapons?|injections?|needles?|surgery|pregnan\w*|kidnap\w*|jump ?scares?|"
    r"pranks?|nightmare)\b", _I)
# Characters other people own. Using them needs a licence (copyright and trademark).
FRANCHISES = [
    "peppa pig", "paw patrol", "bluey", "cocomelon", "spider-man", "spiderman", "spidey",
    "elsa", "anna and elsa", "mickey mouse", "minnie mouse", "disney", "pokemon", "pokémon",
    "pikachu", "super mario", "mario", "sonic", "barbie", "hello kitty", "pj masks",
    "baby shark", "pinkfong", "minecraft", "roblox", "fortnite", "batman", "superman",
    "hulk", "marvel", "avengers", "shrek", "minions", "sesame street", "elmo",
    "thomas the tank", "blippi", "ms rachel", "lego", "hot wheels", "transformers",
    "my little pony", "teletubbies", "dora", "sponge ?bob", "spongebob", "toy story",
]
FRANCHISE = re.compile(r"\b(?:" + "|".join(FRANCHISES) + r")\b", _I)


def _clickbait(title: str) -> str | None:
    letters = [c for c in title if c.isalpha()]
    if len(letters) >= 8 and sum(c.isupper() for c in letters) / len(letters) > .6:
        return "title is mostly capital letters"
    if re.search(r"[!?]{3,}", title):
        return "title stacks !!! or ???"
    emoji = sum(1 for c in title if ord(c) >= 0x1F300)
    if emoji > 3:
        return f"title has {emoji} emoji"
    return None


def scan(title: str, description: str = "", tags: Iterable[str] = ()) -> list[dict[str, str]]:
    """Issues in a child-directed video's text. Each: {issue, detail}."""
    text = "\n".join([title, description, " ".join(tags)])
    out: list[dict[str, str]] = []

    def add(issue: str, m: re.Match[str] | None, why: str) -> None:
        if m:
            out.append({"issue": issue, "detail": f'{why}: "{m.group(0).strip()}"'})

    add("personal_info", PERSONAL_INFO.search(text),
        "asks a child for personal information (COPPA)")
    add("external_link", LINK.search(text), "sends children off YouTube with a link")
    add("engagement_bait", ENGAGEMENT.search(text),
        "asks children to comment, like or turn on notifications (off on made-for-kids)")
    add("purchase_pressure", PURCHASE.search(text), "pressures children to buy")
    add("unsuitable_theme", UNSUITABLE.search(text), "theme not suitable for young children")
    add("franchise", FRANCHISE.search(text), "uses a character or brand someone else owns")
    cb = _clickbait(title)
    if cb:
        out.append({"issue": "clickbait", "detail": f"sensational title: {cb}"})
    return out


def facts(issues: list[dict[str, str]], *, licensed: bool = False,
          paid_promotion: bool = False, near_duplicate: bool = False,
          made_for_kids_set: bool = True) -> dict[str, Any]:
    """The ``context`` facts the kids rules in the publish domain decide on."""
    kinds = {i["issue"] for i in issues}
    return {
        "child_directed": True,
        "made_for_kids_set": made_for_kids_set,
        "collects_child_data": bool(kinds & {"personal_info", "external_link",
                                             "engagement_bait"}),
        "commercial_pressure": "purchase_pressure" in kinds,
        "paid_promotion": paid_promotion,
        "unsuitable_for_kids": bool(kinds & {"unsuitable_theme", "clickbait"}),
        "unlicensed_characters": "franchise" in kinds and not licensed,
        "near_duplicate": near_duplicate,
    }


def _words(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower())) - {"the", "a", "an", "and", "of", "for",
                                                      "to", "in", "with", "kids", "song"}


def near_duplicate(title: str, previous: Iterable[tuple[str, str]],
                   threshold: float = .8) -> str | None:
    """Id of an earlier video whose title is almost the same (YouTube's inauthentic /
    mass-produced content rule), else None. ``previous`` yields (item_id, title)."""
    mine = _words(title)
    if not mine:
        return None
    for item_id, other in previous:
        theirs = _words(other)
        if theirs and len(mine & theirs) / len(mine | theirs) >= threshold:
            return item_id
    return None
