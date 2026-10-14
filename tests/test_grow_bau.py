"""Growing BAU from any terminal: an instruction file any AI coding agent follows (Claude
Code loads it as the `grow-bau` skill) to question itself, find, inspect, test and - only
after the owner says yes - add open-source projects, then rebuild the stick. And a guide
for building the complete stick image outside VS Code. Written before the docs."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".claude" / "skills" / "grow-bau" / "SKILL.md"
BUILD = ROOT / "docs" / "BUILD-ISO.md"


def text():
    return SKILL.read_text()


def test_the_skill_loads_as_an_agent_skill():
    head = text().split("---")[1]
    assert re.search(r"^name: grow-bau$", head, re.M)
    assert re.search(r"^description: .{40,}", head, re.M)


def test_the_loop_questions_itself_before_it_searches_and_tests_before_it_adds():
    t = text()
    steps = ["Ask yourself", "Find", "Inspect", "Test", "The owner decides", "Add", "Rebuild"]
    pos = [t.index(f"## {i}. {s}") for i, s in enumerate(steps, 1)]
    assert pos == sorted(pos)                               # in this order, every time


def test_it_keeps_the_safety_rules():
    t = text().lower()
    for rule in ("never install", "--network none", "licence", "owner says yes",
                 "never mark", "approve", "kids", "abliterated", "secrets",
                 "compliant", "one commit"):
        assert rule in t, rule
    assert "claude.md" in t                                 # the rules it must not break


def test_every_bau_command_it_names_exists():
    from bau.cli import build_parser
    sub = next(a for a in build_parser()._actions if a.dest == "cmd" or
               a.__class__.__name__ == "_SubParsersAction")
    cmds = set(re.findall(r"`bau (\w[\w-]*) (\w[\w-]*)", text() + BUILD.read_text()))
    assert cmds
    for top, verb in cmds:
        assert top in sub.choices, top
        inner = next(a for a in sub.choices[top]._actions
                     if a.__class__.__name__ == "_SubParsersAction")
        assert verb in inner.choices, f"bau {top} {verb}"


def test_it_aims_high_with_measurable_targets():
    t = text()
    assert "## Best case" in t
    best = t[t.index("## Best case"):]
    assert len(re.findall(r"^- \*\*", best, re.M)) >= 6
    assert best.lower().count("measure") >= 3


def test_the_build_guide_works_without_vs_code():
    b = BUILD.read_text()
    for need in ("Run workflow", "Get-FileHash", "wsl --install",
                 "bash image/build-live.sh", "/grow-bau", ".claude/skills/grow-bau/SKILL.md"):
        assert need in b, need
    assert "BUILD-ISO.md" in (ROOT / "docs" / "LIVE-USB.md").read_text()
