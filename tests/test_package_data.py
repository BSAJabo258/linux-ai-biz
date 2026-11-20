"""Every data file BAU reads at run time is in the installed package.

2026-11-20 on the owner's desktop: `sudo bau remote-desktop on` crashed because
data/hq/nftables-remote-desktop.rules was not in pyproject's package-data; the tests read the
source folder, so they passed."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "bau"


def test_every_data_and_ui_file_is_packaged():
    patterns = tomllib.loads((ROOT / "pyproject.toml").read_text())[
        "tool"]["setuptools"]["package-data"]["bau"]
    packaged = {p for pat in patterns for p in PKG.glob(pat) if p.is_file()}
    shipped = {p for top in ("data", "ui") for p in (PKG / top).rglob("*")
               if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".py"}
    missing = sorted(str(p.relative_to(PKG)) for p in shipped - packaged)
    assert not missing, f"not in pyproject.toml package-data: {missing}"
