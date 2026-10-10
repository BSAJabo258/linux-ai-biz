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
    for base in ("hero", "features"):
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
    for base in ("hero", "features"):
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


# ------------------------------------------------------------------ the page, round two

def facts():
    from bau.policy import PolicyEngine
    from bau.regulations import Registry
    from bau.series import Series
    from bau.toolbox import Toolbox
    reg = Registry.load()
    return {"regulations": len(reg.regs), "policies": len(PolicyEngine.load(reg).policies),
            "tools": len(Toolbox().entries), "formats": len(Series(ROOT).formats())}


def test_stats_panel_shows_the_repo_as_it_really_is():
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location("make_art", ART / "make_art.py")
    art = module_from_spec(spec)
    spec.loader.exec_module(art)
    assert art.facts() == facts()                        # computed from the repo, not typed
    for theme in ("dark", "light"):
        text = (ART / f"stats-{theme}.svg").read_text()
        for value in facts().values():
            assert f">{value}<" in text, f"stats-{theme}.svg is stale: run assets/make_art.py"


def test_terminal_demo_types_real_commands():
    for theme in ("dark", "light"):
        text = (ART / f"terminal-{theme}.svg").read_text()
        assert "@keyframes" in text and "prefers-reduced-motion" in text
        for cmd in ("bau toolbox ask", "bau series plan", "bau usage"):
            assert cmd in text, cmd


def test_jarvis_demo_gif_is_a_real_animation_and_not_huge():
    gif = ART / "jarvis-demo.gif"
    data = gif.read_bytes()
    assert data[:6] == b"GIF89a" and data.count(b"\x21\xf9\x04") >= 10   # 10+ frames
    assert len(data) < 6_000_000
    assert "assets/jarvis-demo.gif" in README


def test_readme_uses_github_notice_boxes():
    assert "> [!IMPORTANT]" in README and "> [!TIP]" in README


def test_jarvis_answer_cards_read_like_the_panels():
    """Tool answers on screen use the same readable layouts as the panels, not raw fields."""
    page = (resources.files("bau.ui") / "jarvis.html").read_text()
    for tool in ("usage_today", "toolbox", "plan_episode", "clip_prompt"):
        assert f'c.tool === "{tool}"' in page, tool
    assert "function usageView" in page and "function toolCard" in page


# ------------------------------------------------------------------ round three: the hero

def test_hero_is_cinematic_and_still_calm_on_request():
    for theme in ("dark", "light"):
        text = (ART / f"hero-{theme}.svg").read_text()
        assert "spin-globe" in text                  # the continents roll across the globe
        assert text.count('class="phrase') >= 4      # the typing line cycles what BAU does
        assert "twinkle" in text and "ripple" in text
        assert "prefers-reduced-motion" in text
    readme_top = README[:README.index("## Meet Jarvis")]
    assert 'srcset="assets/hero-dark.svg"' in readme_top


def test_demo_gif_leads_the_page_and_loads_fast():
    gif = (ART / "jarvis-demo.gif").read_bytes()
    assert len(gif) < 2_600_000                       # starts quickly, even on a phone
    first_img = re.findall(r'<img src="([^"]+)"', README)
    assert "assets/jarvis-demo.gif" in first_img[:3]   # right under the hero
    assert (ART / "divider-dark.svg").is_file() and "assets/divider-dark.svg" in README
