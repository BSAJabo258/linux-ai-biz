"""Jarvis's self-modification lab: propose in private, test in a copy, only the owner applies.

Written before the code it tests. The point is the boundary: the repository is untouched
by every model-callable tool, and the live service is untouched even after the owner applies.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from bau.assistant import Assistant
from bau.audit import AuditLog
from bau.selfmod import SelfLab, SelfModError


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "src" / "bau").mkdir(parents=True)
    (root / "src" / "bau" / "__init__.py").write_text("")
    (root / "tests").mkdir()
    (root / "docs").mkdir()
    (root / "src" / "bau" / "thing.py").write_text("VALUE = 1\n")
    (root / "tests" / "test_thing.py").write_text("from bau.thing import VALUE\n\n"
                                                  "def test_value():\n    assert VALUE == 1\n")
    (root / "docs" / "HOW.md").write_text("# How\n")
    (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\npythonpath = ['src']\n")
    return root


def ok(work, cmd, timeout):
    return subprocess.CompletedProcess(cmd, 0, "1 passed\n", "")


def bad(work, cmd, timeout):
    return subprocess.CompletedProcess(cmd, 1, "1 failed\n", "")


def lab(repo, home, runner=ok):
    return SelfLab(root=repo, home=home, audit=AuditLog(home / "audit" / "chain.jsonl"),
                   runner=runner)


def test_a_proposal_never_touches_the_repository_until_the_owner_applies(repo, tmp_path):
    s = lab(repo, tmp_path / "home")
    out = s.propose({"src/bau/thing.py": "VALUE = 2\n"}, "make the value two")
    assert (repo / "src" / "bau" / "thing.py").read_text() == "VALUE = 1\n"
    work = tmp_path / "home" / "selflab" / out["proposal"] / "work"
    assert (work / "src" / "bau" / "thing.py").read_text() == "VALUE = 2\n"
    assert s.test(out["proposal"])["passed"]
    assert "+VALUE = 2" in s.diff(out["proposal"])["diff"]
    assert "Apply " in s.card(out["proposal"])["summary"]
    s.apply(out["proposal"], "human:owner")
    assert (repo / "src" / "bau" / "thing.py").read_text() == "VALUE = 2\n"


def test_failed_or_missing_tests_block_apply(repo, tmp_path):
    s = lab(repo, tmp_path / "home", runner=bad)
    out = s.propose({"src/bau/thing.py": "VALUE = 2\n"}, "make the value two")
    with pytest.raises(SelfModError, match="tests"):
        s.card(out["proposal"])
    assert not s.test(out["proposal"])["passed"]
    with pytest.raises(SelfModError, match="tests"):
        s.apply(out["proposal"], "human:owner")
    assert (repo / "src" / "bau" / "thing.py").read_text() == "VALUE = 1\n"


def test_only_a_human_applies_and_a_changed_file_is_a_conflict(repo, tmp_path):
    s = lab(repo, tmp_path / "home")
    out = s.propose({"src/bau/thing.py": "VALUE = 2\n"}, "make the value two")
    s.test(out["proposal"])
    with pytest.raises(PermissionError):
        s.apply(out["proposal"], "jarvis")
    (repo / "src" / "bau" / "thing.py").write_text("VALUE = 3\n")
    with pytest.raises(SelfModError, match="changed"):
        s.apply(out["proposal"], "human:owner")
    assert (repo / "src" / "bau" / "thing.py").read_text() == "VALUE = 3\n"


def test_existing_tests_are_not_rewritten(repo, tmp_path):
    s = lab(repo, tmp_path / "home")
    with pytest.raises(SelfModError, match="existing tests"):
        s.propose({"tests/test_thing.py": "def test_nothing():\n    assert True\n"}, "weaken")
    assert s.propose({"tests/test_extra.py": "def test_extra():\n    assert True\n"},
                     "add a test")["files"] == ["tests/test_extra.py"]


def test_the_lab_refuses_escape_secrets_and_non_source(repo, tmp_path):
    s = lab(repo, tmp_path / "home")
    for path in ("../outside.py", "/etc/passwd", "src/bau/.env", "src/bau/key.py",
                 "README.md", "src/bau/thing.exe"):
        with pytest.raises(SelfModError):
            s.propose({path: "x\n"}, "no")
    with pytest.raises(SelfModError):
        s.read("../thing.py")
    with pytest.raises(SelfModError):
        s.search("VALUE", "../")
    with pytest.raises(SelfModError):
        s.test("sm_00000000", ["/etc/passwd"])


def test_search_and_read_stay_inside_the_repository(repo, tmp_path):
    s = lab(repo, tmp_path / "home")
    assert s.search("VALUE")["hits"][0]["path"] == "src/bau/thing.py"
    assert "VALUE" in s.read("src/bau/thing.py")["text"]
    assert s.status()["proposals"] == []


def test_jarvis_stages_apply_and_needs_the_owner_to_confirm(repo, tmp_path):
    a = Assistant(tmp_path / "home", None, {}, "human:owner",
                  AuditLog(tmp_path / "home" / "audit" / "chain.jsonl", key=b""))
    a.selflab = lab(repo, tmp_path / "home")
    out = a._run_tool("self_propose", {"files": {"src/bau/thing.py": "VALUE = 2\n"},
                                       "reason": "make the value two"})[0]
    pid = out["proposal"]
    assert a._run_tool("self_test", {"proposal": pid})[0]["passed"]
    staged = a._run_tool("self_apply", {"proposal": pid})[0]
    assert staged["status"] == "PENDING_OWNER_CONFIRMATION"
    assert (repo / "src" / "bau" / "thing.py").read_text() == "VALUE = 1\n"
    with pytest.raises(PermissionError):
        a.confirm(staged["pending_id"], True, "jarvis")
    a.confirm(staged["pending_id"], True, "human:owner")
    assert (repo / "src" / "bau" / "thing.py").read_text() == "VALUE = 2\n"


def test_real_pytest_runs_against_the_private_copy(repo, tmp_path):
    s = SelfLab(root=repo, home=tmp_path / "home",
                audit=AuditLog(tmp_path / "home" / "audit" / "chain.jsonl"))
    out = s.propose({"src/bau/thing.py": "VALUE = 2\n",
                     "tests/test_value.py": "from bau.thing import VALUE\n\n"
                                           "def test_value():\n    assert VALUE == 2\n"},
                    "make the value two")
    result = s.test(out["proposal"], ["tests/test_value.py"])
    assert result["passed"], result["output"]
    assert (repo / "src" / "bau" / "thing.py").read_text() == "VALUE = 1\n"


def test_protected_safety_files_are_read_but_never_changed(repo, tmp_path):
    from bau import selfmod
    s = SelfLab(root=repo, home=tmp_path / "home", audit=AuditLog(tmp_path / "a.jsonl"))
    for rel in ("src/bau/gateway.py", "src/bau/selfmod.py", "src/bau/autopilot.py",
                "src/bau/security/x.py", "src/bau/data/policies/p.yaml", "tests/conftest.py"):
        with pytest.raises(SelfModError, match="protected"):
            s.propose({rel: "X = 1\n"}, "loosen a rule")
    assert "src/bau/gateway.py" in selfmod.PROTECTED
    # a record edited on disk to name a protected file is refused at apply time too
    r = s.propose({"src/bau/thing.py": "VALUE = 2\n"}, "bump")
    pd = tmp_path / "home" / "selflab" / r["proposal"]
    rec = json.loads((pd / "proposal.json").read_text())
    rec["files"]["src/bau/gateway.py"] = "OPEN = True\n"
    rec["tested"], rec["test"] = True, {"exit": 0}
    (pd / "proposal.json").write_text(json.dumps(rec))
    with pytest.raises(SelfModError, match="protected"):
        s.apply(r["proposal"], "human:owner")
