"""The docs and README must not invent things. Every `bau ...` command they show is a real
command, every relative link opens, and every repo path they name exists. Cheap: no
network, no model, a second or two. It catches the mistakes a writer (human or AI) makes
from memory instead of checking."""

import argparse
import re
from pathlib import Path

from bau.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]
PAGES = [ROOT / "README.md", ROOT / "CLAUDE.md", *sorted((ROOT / "docs").rglob("*.md"))]
SPEC = ROOT / "docs" / "spec"            # the owner's master spec: a plan, not a manual
CMD = re.compile(r"(?:^|[\s;&|(`$])(?:sudo\s+)?bau\s+([a-z][\w-]*)(?:\s+([a-z][\w-]*))?")


def pages():
    return [p for p in PAGES if SPEC not in p.parents]


def commands() -> dict[str, set[str]]:
    """Top-level command -> its subcommands (empty set when it has none)."""
    tree = {}
    for action in build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                kids = set()
                for a in sub._actions:
                    if isinstance(a, argparse._SubParsersAction):
                        kids |= set(a.choices)
                tree[name] = kids
    return tree


def code_spans(text: str):
    """Inline `code` and fenced code blocks: where commands are shown to be typed."""
    for block in re.findall(r"```[^\n]*\n(.*?)```", text, re.S):
        yield from block.splitlines()
    yield from re.findall(r"`([^`\n]+)`", re.sub(r"```.*?```", "", text, flags=re.S))


def test_every_bau_command_in_the_docs_exists():
    tree, wrong = commands(), []
    for page in pages():
        for span in code_spans(page.read_text()):
            for m in CMD.finditer(span):
                cmd, sub = m.group(1), m.group(2)
                if cmd not in tree:
                    wrong.append(f"{page.relative_to(ROOT)}: bau {cmd}")
                elif tree[cmd] and sub and sub not in tree[cmd]:
                    wrong.append(f"{page.relative_to(ROOT)}: bau {cmd} {sub}")
    assert not wrong, "commands that do not exist:\n" + "\n".join(sorted(set(wrong)))


def test_every_relative_link_opens():
    broken = []
    for page in pages():
        for target in re.findall(r"\]\(([^)\s]+)\)", page.read_text()):
            if re.match(r"[a-z]+:|#", target):
                continue
            path = (page.parent / target.split("#")[0]).resolve()
            if not path.exists():
                broken.append(f"{page.relative_to(ROOT)} -> {target}")
    assert not broken, "links to nothing:\n" + "\n".join(broken)


def test_every_repo_path_named_in_the_docs_exists():
    missing = []
    for page in pages():
        for span in code_spans(page.read_text()):
            for m in re.finditer(r"(?<![\w/.$~-])((?:installer|image|src/bau|tests|docs|assets)"
                                 r"/[\w./-]*[\w])", span):
                path = m.group(1)
                if "..." in path or path.startswith("image/live-build/config/includes"):
                    continue
                py = ROOT / (path.rsplit(".", 1)[0] + ".py")     # src/bau/jobs.Job
                if not ((ROOT / path).exists() or any(ROOT.glob(path + "*")) or py.exists()):
                    missing.append(f"{page.relative_to(ROOT)}: {path}")
    assert not missing, "paths that do not exist:\n" + "\n".join(sorted(set(missing)))
