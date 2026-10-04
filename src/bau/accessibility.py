"""Accessibility tooling (spec §28-30).

* ShortcutRegistry - every critical command has a keyboard shortcut; conflicts and
  unconfirmed dangerous shortcuts are rejected (spec §29).
* lint_html        - static checks for common WCAG 2.2 AA failures. A clean lint is
  necessary, not sufficient: spec §30's manual screen-reader/zoom/keyboard pass still
  has to be done by a person.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .home import bau_home
from .store import YamlStore

RESERVED = {"ctrl+c", "ctrl+v", "ctrl+x", "ctrl+z", "ctrl+w", "ctrl+t", "ctrl+n", "ctrl+q",
            "alt+f4", "tab", "shift+tab", "escape", "enter", "space"}


class ShortcutRegistry:
    def __init__(self, path: Path | None = None):
        self.store = YamlStore(path or (bau_home() / "config" / "shortcuts.yaml"),
                               {"shortcuts": {}})

    def add(self, command: str, key: str, danger_level: str = "LOW",
            confirmation_required: bool = False, remappable: bool = True) -> dict[str, Any]:
        key = key.lower().replace(" ", "")
        if key in RESERVED:
            raise ValueError(f"{key} is reserved by the OS/browser/assistive tech")
        if danger_level in ("HIGH", "CRITICAL") and not confirmation_required:
            raise ValueError("dangerous commands need a confirmation step")
        data = self.store.load()
        clash = [c for c, s in data["shortcuts"].items() if s["default_key"] == key
                 and c != command]
        if clash:
            raise ValueError(f"{key} already bound to {clash[0]}")
        data["shortcuts"][command] = {"command": command, "default_key": key,
                                      "danger_level": danger_level,
                                      "confirmation_required": confirmation_required,
                                      "remappable": remappable, "conflicts": []}
        self.store.save(data)
        return data["shortcuts"][command]

    def all(self) -> dict[str, Any]:
        return self.store.load()["shortcuts"]


class _A11y(HTMLParser):
    FOCUSABLE = {"a", "button", "input", "select", "textarea"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.issues: list[dict[str, Any]] = []
        self.lang = False
        self.title = False
        self.headings: list[int] = []
        self.labels_for: set[str] = set()
        self.inputs: list[tuple[str | None, dict[str, str | None], int]] = []
        self.skip_link = False
        self.stack: list[tuple[str, dict[str, str | None], list[str]]] = []
        self.main = False

    def err(self, rule: str, msg: str) -> None:
        self.issues.append({"rule": rule, "message": msg, "line": self.getpos()[0]})

    def handle_starttag(self, tag: str, attrs_l: list[tuple[str, str | None]]) -> None:
        a = dict(attrs_l)
        if tag == "html" and a.get("lang"):
            self.lang = True
        if tag == "title":
            self.title = True
        if tag == "main" or a.get("role") == "main":
            self.main = True
        if re.fullmatch(r"h[1-6]", tag):
            lvl = int(tag[1])
            if self.headings and lvl > self.headings[-1] + 1:
                self.err("1.3.1", f"heading jumps from h{self.headings[-1]} to h{lvl}")
            self.headings.append(lvl)
        if tag == "img" and a.get("alt") is None:
            self.err("1.1.1", "img without alt attribute")
        if tag == "label" and a.get("for"):
            self.labels_for.add(a["for"] or "")
        if tag in ("input", "select", "textarea") and a.get("type") not in ("hidden", "submit",
                                                                           "button"):
            self.inputs.append((a.get("id"), a, self.getpos()[0]))
        ti = a.get("tabindex")
        if ti and ti.lstrip("-").isdigit() and int(ti) > 0:
            self.err("2.4.3", "positive tabindex breaks logical focus order")
        if tag == "a" and (a.get("href") or "").startswith("#") and not self.skip_link \
                and len(self.headings) == 0:
            self.skip_link = True
        if a.get("onclick") is not None and tag not in self.FOCUSABLE and a.get("tabindex") \
                is None and a.get("role") is None:
            self.err("2.1.1", f"<{tag} onclick> is mouse-only (no role/tabindex)")
        self.stack.append((tag, a, []))

    def handle_data(self, data: str) -> None:
        if self.stack and data.strip():
            self.stack[-1][2].append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        while self.stack:
            t, a, text = self.stack.pop()
            if self.stack and text:
                self.stack[-1][2].extend(text)
            if t == tag:
                if t in ("button", "a") and not text and not a.get("aria-label") \
                        and not a.get("aria-labelledby") and not a.get("title"):
                    self.err("4.1.2", f"<{t}> has no accessible name")
                break


def lint_html(html: str) -> list[dict[str, Any]]:
    p = _A11y()
    p.feed(html)
    p.close()
    if not p.lang:
        p.issues.append({"rule": "3.1.1", "message": "<html> has no lang", "line": 1})
    if not p.title:
        p.issues.append({"rule": "2.4.2", "message": "page has no <title>", "line": 1})
    if not p.skip_link:
        p.issues.append({"rule": "2.4.1", "message": "no skip link before content",
                         "line": 1})
    if not p.main:
        p.issues.append({"rule": "1.3.1", "message": "no <main> landmark", "line": 1})
    for iid, a, line in p.inputs:
        if not (iid and iid in p.labels_for) and not a.get("aria-label") \
                and not a.get("aria-labelledby"):
            p.issues.append({"rule": "3.3.2", "message": "form field without a label",
                             "line": line})
    if re.search(r"outline\s*:\s*(none|0)", html) and ":focus-visible" not in html:
        p.issues.append({"rule": "2.4.7", "message": "focus outline removed without "
                         ":focus-visible replacement", "line": 1})
    if "prefers-reduced-motion" not in html and re.search(r"animation|transition", html):
        p.issues.append({"rule": "2.3.3", "message": "motion without prefers-reduced-motion",
                         "line": 1})
    return p.issues


ACCEPTANCE = ["tab through everything", "shift+tab through everything", "enter everything",
              "escape everything", "arrow through menus", "screen reader test", "zoom 200%",
              "high-contrast test", "reduced-motion test", "mobile test"]
