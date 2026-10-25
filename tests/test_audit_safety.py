"""Holes found by the code audit of 2026-10-25 (safety model), each written as a failing
test first. CLAUDE.md: approvals are human-only and signed; kids content only to platforms
that allow kids; consequential actions wait on HOLD; tool results reach models as data."""

import json
import subprocess
import sys

from bau.factories import FactoryRun, FactoryRunner


# ------------------------------------------------------------------ factory gates
class _Decision:
    status = "PASS_WITH_REVIEW"

    def to_dict(self):
        return {"status": self.status}

    def may_proceed(self, approved):
        return approved

    def blocking(self):
        return []


class _Engine:
    def evaluate(self, domain, facts, on=None):
        return _Decision()


def test_a_gate_needing_a_signed_approval_does_not_pass_on_any_string(tmp_path):
    # Before: approved = domain in run.approvals, so "/dev/null" passed the gate.
    hooks = {"agent": None, "tool": None,
             "approval_ok": lambda cap, run, ref: ref == "valid-sig"}
    runner = FactoryRunner(_Engine(), hooks, home=tmp_path)
    runner.defs = {"t": {"stages": [{"id": "g", "type": "gate", "domain": "monetize"}]}}
    run = FactoryRun(run_id="fr_test", factory="t", objective="x",
                     gate_facts={"monetize": {}}, approvals={"monetize": "/dev/null"})
    assert runner.advance(run).status == "WAITING_GATE"
    run.approvals["monetize"] = "valid-sig"
    assert runner.advance(run).status == "COMPLETED"


# ------------------------------------------------------------------ the CLI's human gates
def _bau(home, *args, stdin=subprocess.DEVNULL):
    return subprocess.run([sys.executable, "-m", "bau.cli", *args], capture_output=True,
                          text=True, stdin=stdin, timeout=120,
                          env={"BAU_HOME": str(home), "PATH": "/usr/bin:/bin",
                               "HOME": str(home)})


def test_registry_add_cannot_approve_and_needs_a_person(tmp_path):
    # Before: `bau registry add provider rec.yaml` with status APPROVED, from any process.
    assert _bau(tmp_path, "init").returncode == 0
    rec = tmp_path / "rec.json"
    rec.write_text(json.dumps({"provider_id": "evil", "data_sent": [], "data_retained": "no",
                               "training_on_customer_data": False, "jurisdiction": "US",
                               "commercial_rights": True, "terms_url": "https://x.example",
                               "status": "APPROVED"}))
    r = _bau(tmp_path, "registry", "add", "provider", str(rec))
    assert r.returncode != 0
    reg = (tmp_path / "registry" / "capabilities.yaml").read_text()
    assert "evil" not in reg
