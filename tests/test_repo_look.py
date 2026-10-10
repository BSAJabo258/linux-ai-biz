"""The repository's face: an animated banner and feature cards for GitHub (dark and light),
a real Jarvis screenshot, and Mission Control in the same look as Jarvis. Written before
the artwork it tests."""

import re
import xml.etree.ElementTree as ET
from importlib import resources
from pathlib import Path

from bau.accessibility import lint_html

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "assets"
README = (ROOT / "README.md").read_text()


def svgs():
    return sorted(ART.glob("*.svg"))


def test_banner_and_cards_come_in_dark_and_light():
    names = {p.stem for p in svgs()}
    for base in ("banner", "features"):
        assert {f"{base}-dark", f"{base}-light"} <= names, base


def test_svgs_are_valid_self_contained_and_calm_on_request():
    assert svgs()
    for p in svgs():
        text = p.read_text()
        root = ET.fromstring(text)                         # well-formed XML
        assert root.tag.endswith("svg") and root.get("viewBox"), p.name
        assert "<script" not in text and "foreignObject" not in text, p.name
        assert not re.search(r'(href|src)="https?://', text), f"{p.name} loads from outside"
        assert "@import" not in text, p.name
        if "@keyframes" in text or "<animate" in text:
            assert "prefers-reduced-motion" in text, f"{p.name} must stop for reduced motion"
        assert re.search(r"<title[^>]*>[^<]{3,}</title>", text), f"{p.name} needs a title"


def test_readme_shows_the_artwork_with_theme_switching_and_alt_text():
    for base in ("banner", "features"):
        assert f'srcset="assets/{base}-dark.svg"' in README
        assert f'src="assets/{base}-light.svg"' in README
        assert 'media="(prefers-color-scheme: dark)"' in README
    for alt in re.findall(r'<img[^>]*>', README):
        assert re.search(r'alt="[^"]{6,}"', alt), alt
    assert (ART / "jarvis-hud.png").is_file() and "assets/jarvis-hud.png" in README
    assert "```mermaid" in README
    assert "actions/workflows/ci.yml/badge.svg" in README


def test_readme_still_makes_no_compliance_claims():
    plain = re.sub(r'never claims to be "compliant"', "", README)
    assert not re.search(r"\b(is|are|fully|100%) compliant\b|guaranteed|risk-free", plain, re.I)


def test_mission_control_has_the_jarvis_look_and_stays_accessible():
    page = (resources.files("bau.ui") / "page.html").read_text()
    assert lint_html(page) == []
    assert "--glow" in page and "--gold" in page              # the Jarvis palette
    assert "prefers-reduced-motion" in page and "prefers-color-scheme: light" in page
    assert "@import" not in page and "https://" not in page   # works offline on the laptop
