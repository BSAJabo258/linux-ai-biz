import datetime as dt
import shutil
from pathlib import Path

import pytest
import yaml

from bau.home import shipped_data
from bau.policy import PolicyEngine
from bau.regulations import Registry

ON = dt.date(2026, 10, 4)
WHEN = dt.datetime(2026, 10, 4, 15, 0, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "bauhome"
    home.mkdir()
    monkeypatch.setenv("BAU_HOME", str(home))
    monkeypatch.setenv("BAU_AUDIT_KEY", str(tmp_path / "no-key"))
    return home


@pytest.fixture
def engine():
    return PolicyEngine.load(Registry.load(shipped_data() / "regulations"),
                             shipped_data() / "policies")


@pytest.fixture
def active_engine(tmp_path):
    """Engine where every in-force rule has been signed off by a reviewer."""
    regs = tmp_path / "regs_active"
    regs.mkdir()
    for f in (shipped_data() / "regulations").glob("*.yaml"):
        docs = yaml.safe_load(f.read_text())
        for d in docs:
            if d["legal_status"] != "proposed":
                d["bau_status"] = "ACTIVE"
                d["reviewed_by"] = "test-counsel"
        (regs / f.name).write_text(yaml.safe_dump(docs, sort_keys=False))
    pol = tmp_path / "pols"
    shutil.copytree(shipped_data() / "policies", pol)
    return PolicyEngine.load(Registry.load(regs), pol)


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent
