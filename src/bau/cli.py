"""`bau` command line - keyboard-only access to every critical control (spec §29).

Exit codes: 0 proceed / ok, 2 human review or approval required,
3 blocked / unknown / incomplete / conflict, 4 usage or data error.
"""

from __future__ import annotations

import argparse
import datetime as dt
import getpass
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from . import __version__, backup, hardware, wipe_gate
from .audit import AuditLog, ref
from .claims import ClaimsRegistry, scan
from .decision import Decision, Status
from .home import bau_home, data_dir, init_home
from .policy import PolicyEngine
from .regulations import Registry, RegistryError, promote

EXIT_OK, EXIT_REVIEW, EXIT_BLOCKED, EXIT_ERROR = 0, 2, 3, 4


def _out(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _load(path: str) -> Any:
    text = Path(path).read_text()
    return json.loads(text) if path.endswith(".json") else yaml.safe_load(text)


def _engine() -> PolicyEngine:
    return PolicyEngine.load(Registry.load())


def _exit_for(status: Status) -> int:
    if status in (Status.PASS, Status.NOT_APPLICABLE):
        return EXIT_OK
    if status == Status.PASS_WITH_REVIEW:
        return EXIT_REVIEW
    return EXIT_BLOCKED


def _actor() -> str:
    return f"human:{getpass.getuser()}" if sys.stdin.isatty() else f"process:{getpass.getuser()}"


def _decision(d: Decision, kind: str, evidence: bool) -> int:
    body = d.to_dict()
    if evidence:
        from .evidence import write_package
        body["evidence_path"] = str(write_package(kind, d.to_dict(), _actor()))
    _out(body)
    return _exit_for(d.status)


def _key(env: str, default: str) -> bytes:
    return Path(os.environ.get(env, default)).read_bytes().strip()


# ---------------------------------------------------------------- commands

def cmd_init(a: argparse.Namespace) -> int:
    home = init_home(Path(a.home) if a.home else None, overwrite_data=a.refresh_data)
    from .runtime import seed_registry
    seed_registry(home)
    log = AuditLog(home / "audit" / "chain.jsonl")
    if not any(True for _ in log.records()):
        log.append("system.genesis", _actor(), {"version": __version__})
    _out({"bau_home": str(home), "audit": log.verify()[1]})
    return EXIT_OK


def cmd_status(a: argparse.Namespace) -> int:
    from .status import dashboard
    d = dashboard()
    if a.brief:
        d = {k: v for k, v in d.items() if k != "items"}
    _out(d)
    return EXIT_OK if d["overall"] == "GREEN" else EXIT_REVIEW


def cmd_reg(a: argparse.Namespace) -> int:
    on = dt.date.fromisoformat(a.on) if getattr(a, "on", None) else dt.date.today()
    if a.reg_cmd == "validate":
        try:
            reg = Registry.load()
            eng = PolicyEngine.load(reg)
        except (RegistryError, ValueError) as e:
            print(str(e), file=sys.stderr)
            return EXIT_ERROR
        _out({"regulations": len(reg.regs), "policies": len(eng.policies), "valid": True})
        return EXIT_OK
    reg = Registry.load()
    if a.reg_cmd == "list":
        rows = [{"reg_id": r.reg_id, "jurisdiction": r["jurisdiction"],
                 "legal_status": r["legal_status"], "bau_status": r["bau_status"],
                 "applicability": r.applicability(on), "next_review": r["next_review"]}
                for r in reg]
        _out(rows)
    elif a.reg_cmd == "show":
        r = reg.get(a.reg_id)
        if not r:
            return EXIT_ERROR
        _out(r.raw)
    elif a.reg_cmd == "due":
        _out({"review_due": [r.reg_id for r in reg.due_for_review(on, a.days)],
              "taking_effect": [{"reg_id": r.reg_id, "date": r["effective_date"]}
                                for r in reg.upcoming(on, a.days)]})
    elif a.reg_cmd == "watch":
        from .regulations import watch
        res = watch(reg, bau_home() / "regulations" / ".watch-state.json", on)
        AuditLog().append("regulation.watch", "system:regwatch",
                          {"checked": res["checked"], "changed": len(res["changed"]),
                           "unreachable": len(res["unreachable"])})
        _out(res)
        return EXIT_REVIEW if res["changed"] else EXIT_OK
    elif a.reg_cmd == "promote":
        if not sys.stdin.isatty():
            print("promotion must be done interactively by a human reviewer", file=sys.stderr)
            return EXIT_ERROR
        path = next((p for p in data_dir("regulations").glob("*.yaml")
                     if any(r.get("reg_id") == a.reg_id
                            for r in yaml.safe_load(p.read_text()) or [])), None)
        if path is None or path.is_relative_to(Path(__file__).parent):
            print("run `bau init` first; shipped data is read-only", file=sys.stderr)
            return EXIT_ERROR
        rec = promote(path, a.reg_id, a.to, a.reviewer, on)
        AuditLog().append("regulation.promoted", f"human:{a.reviewer}",
                          {"reg_id": a.reg_id, "to": a.to})
        _out(rec)
    return EXIT_OK


def cmd_gate(a: argparse.Namespace) -> int:
    facts = _load(a.facts)
    d = _engine().evaluate(a.domain, facts, scope=a.scope,
                           on=dt.date.fromisoformat(a.on) if a.on else None)
    return _decision(d, f"gate.{a.domain}", a.evidence)


def _comms_stores():
    from .comms.consent import ConsentLedger, SuppressionList
    return ConsentLedger(), SuppressionList()


def _allowed_signers() -> Path:
    return Path(os.environ.get("BAU_ALLOWED_SIGNERS", "/etc/bau/allowed_signers"))


def _content_hash(obj: Any) -> str:
    from .audit import canonical, sha256
    return sha256(canonical(obj))


def _approved(path: str | None, capability: str, request_id: str, content: Any) -> bool:
    """True only for a valid, unexpired, human-signed approval of exactly this request
    AND exactly this content: editing the message after approval voids the approval."""
    if not path:
        return False
    from .security.permissions import SshApprovals, load_approval
    ap = load_approval(Path(path))
    ok = (ap.request_id == request_id
          and ap.scope.get("bound_sha256") == _content_hash(content)
          and SshApprovals(_allowed_signers()).verify(ap, capability))
    AuditLog().append("approval.checked", _actor(), {"request_id": request_id,
                                                     "capability": capability,
                                                     "approver": ap.approver, "valid": ok})
    if not ok:
        print("approval rejected: wrong request, capability, signer, content, or expired",
              file=sys.stderr)
    return ok


def cmd_approve(a: argparse.Namespace) -> int:
    from .security.permissions import Approval, SshApprovals
    now = dt.datetime.now(dt.UTC)
    ap = Approval(request_id=a.request_id, capability=a.capability, requester=a.requester,
                  approver=f"human:{getpass.getuser()}", approved_at=now.isoformat(),
                  expires_at=(now + dt.timedelta(minutes=a.minutes)).isoformat(),
                  scope=json.loads(a.scope) if a.scope else {})
    ap.scope["bound_sha256"] = _content_hash(_load(a.bind))
    if a.evidence:  # show the human exactly what they are approving
        print(Path(a.evidence).read_text()[:4000], file=sys.stderr)
    SshApprovals(_allowed_signers()).sign(ap, Path(a.key).expanduser())
    Path(a.out).write_text(json.dumps(ap.__dict__, indent=2))
    AuditLog().append("approval.granted", ap.approver, {"request_id": a.request_id,
                                                        "capability": a.capability,
                                                        "expires_at": ap.expires_at})
    _out({"approval": a.out, "expires_at": ap.expires_at})
    return EXIT_OK


def cmd_email(a: argparse.Namespace) -> int:
    from .comms import dns_auth
    from .comms import email as em
    if a.email_cmd == "preflight":
        ledger, supp = _comms_stores()
        wl = em.WirelessDomains(bau_home() / "compliance" / "fcc_wireless_domains.txt")
        claims = ClaimsRegistry(bau_home() / "compliance" / "claims.yaml")
        msg = _load(a.message)
        approved = _approved(a.approval, "email.send.commercial", msg.get("campaign_id", ""),
                             msg)
        rep = em.preflight(msg, _load(a.recipients), _load(a.sender), _engine(),
                           ledger, supp, wl, claims, approved=approved)
        body = rep.to_dict()
        if a.evidence:
            from .evidence import write_package
            body["evidence_path"] = str(write_package("email.preflight", body, _actor()))
        _out(body)
        if not rep.message_decision.may_proceed(approved):
            return _exit_for(rep.message_decision.status)
        return EXIT_OK if rep.sendable else EXIT_BLOCKED
    if a.email_cmd == "check-dns":
        _out(dns_auth.check_domain(a.domain, a.selector or []))
        return EXIT_OK
    if a.email_cmd == "headers":
        _out(em.unsubscribe_headers(a.url, a.mailto))
        return EXIT_OK
    if a.email_cmd == "import-wireless-list":
        src = Path(a.file).read_text().splitlines()
        domains = sorted({ln.strip().lower() for ln in src
                          if ln.strip() and not ln.startswith("#")})
        dst = bau_home() / "compliance" / "fcc_wireless_domains.txt"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(f"# fetched_at: {a.fetched_at}\n" + "\n".join(domains) + "\n")
        AuditLog().append("email.wireless_list_imported", _actor(),
                          {"domains": len(domains), "fetched_at": a.fetched_at})
        _out({"imported": len(domains), "path": str(dst)})
        return EXIT_OK
    if a.email_cmd == "suppress":
        ledger, supp = _comms_stores()
        supp.add(a.address, a.reason)
        ledger.withdraw(a.address, channel=None)
        AuditLog().append("suppression.added", _actor(), {"subject": ref(a.address),
                                                          "reason": a.reason})
        _out({"suppressed": ref(a.address)})
        return EXIT_OK
    if a.email_cmd == "unsubscribe":
        from .comms.consent import UnsubscribeTokens
        ledger, supp = _comms_stores()
        tokens = UnsubscribeTokens(_key("BAU_UNSUB_KEY", "/etc/bau/unsubscribe.key"))
        skey, list_id = tokens.parse(a.token)
        supp.add_key(skey, f"unsubscribe:{list_id}")
        n = ledger.withdraw_where(lambda c: supp.key(c) == skey)
        AuditLog().append("email.unsubscribed", "subject", {"subject": "ref:" + skey[:32],
                                                            "list": list_id, "consents": n})
        _out({"unsubscribed": True, "list": list_id})
        return EXIT_OK
    return EXIT_ERROR


def cmd_sms(a: argparse.Namespace) -> int:
    from .comms import sms
    ledger, supp = _comms_stores()
    if a.sms_cmd == "preflight":
        rid, d = sms.preflight(_load(a.message), _load(a.recipient), _engine(), ledger, supp)
        body = d.to_dict()
        body["recipient"] = rid
        _out(body)
        return _exit_for(d.status)
    if a.sms_cmd == "inbound":
        revoked = sms.handle_inbound(a.text, a.number, ledger, supp)
        if revoked:
            AuditLog().append("sms.revocation", "subject", {"subject": ref(a.number)})
        _out({"revocation": revoked})
        return EXIT_OK
    return EXIT_ERROR


def cmd_consent(a: argparse.Namespace) -> int:
    ledger, _ = _comms_stores()
    rec = ledger.record(a.contact, a.channel, a.purpose, a.basis, a.source, a.text_version,
                        a.evidence_ref, a.jurisdiction, wireless_authorized=a.wireless_authorized)
    AuditLog().append("consent.recorded", _actor(), {"subject": ref(a.contact),
                                                     "consent_id": rec.consent_id,
                                                     "basis": a.basis, "channel": a.channel})
    _out({"consent_id": rec.consent_id, "expires_at": rec.expires_at})
    return EXIT_OK


def cmd_subscription(a: argparse.Namespace) -> int:
    from .commerce.subscriptions import check_offer
    d = check_offer(_load(a.offer), _engine(), a.country, a.region)
    return _decision(d, "subscription.offer", a.evidence)


def cmd_disclosure(a: argparse.Namespace) -> int:
    from .disclosure import Provenance, check_publication
    p = Provenance(**_load(a.artifact))
    d = check_publication(p, _load(a.context), _engine())
    body = d.to_dict()
    body["suggested_label"] = p.suggested_label()
    _out(body)
    return _exit_for(d.status)


def cmd_monetize(a: argparse.Namespace) -> int:
    from .commerce.ip import IPAsset, check_monetization
    raw = _load(a.asset)
    raw["owners"] = {k: Decimal(str(v)) for k, v in raw.get("owners", {}).items()}
    raw["royalty_splits"] = {k: Decimal(str(v)) for k, v in raw.get("royalty_splits", {}).items()}
    d = check_monetization(IPAsset(**raw), _engine(), a.market)
    return _decision(d, "ip.monetize", a.evidence)


def cmd_claims(a: argparse.Namespace) -> int:
    hits = scan(Path(a.file).read_text())
    _out({"hits": hits})
    return EXIT_REVIEW if hits else EXIT_OK


def cmd_tax(a: argparse.Namespace) -> int:
    from .commerce import tax
    phys = {"yes": True, "no": False, "unknown": None}[a.physical_presence]
    res = tax.assess(a.jurisdiction, Decimal(a.sales), a.transactions, tax.load_rules(), phys,
                     dt.date.today(), a.marketplace_only)
    _out(res)
    return EXIT_OK if res["status"] == tax.NONE else EXIT_REVIEW


def cmd_dsr(a: argparse.Namespace) -> int:
    from .privacy.dsr import DSRManager, as_dict
    m = DSRManager()
    if a.dsr_cmd == "open":
        req = m.open(a.subject, a.jurisdiction, a.rights)
        _out(as_dict(req))
    elif a.dsr_cmd == "verify-identity":
        req = m.load(a.request_id)
        req.identity_verified = True
        m.save(req)
        _out({"request_id": req.request_id, "identity_verified": True})
    elif a.dsr_cmd == "store":
        req = m.load(a.request_id)
        m.record_store(req, a.store, a.outcome, a.note or "")
        _out({"open_stores": req.open_stores()})
    elif a.dsr_cmd == "complete":
        try:
            req = m.complete(m.load(a.request_id))
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return EXIT_BLOCKED
        _out(as_dict(req))
    elif a.dsr_cmd == "overdue":
        _out([as_dict(r) for r in m.overdue()])
    return EXIT_OK


def cmd_audit(a: argparse.Namespace) -> int:
    log = AuditLog()
    if a.audit_cmd == "verify":
        ok, msg = log.verify()
        _out({"ok": ok, "detail": msg})
        return EXIT_OK if ok else EXIT_BLOCKED
    if a.audit_cmd == "anchor":
        _out(log.anchor())
    elif a.audit_cmd == "tail":
        recs = list(log.records())[-a.n:]
        _out(recs)
    return EXIT_OK


def cmd_secrets(a: argparse.Namespace) -> int:
    from .security.secrets_scan import scan_path
    found = scan_path(Path(a.path))
    _out({"findings": found})
    return EXIT_BLOCKED if found else EXIT_OK


def cmd_sentinel(a: argparse.Namespace) -> int:
    from dataclasses import asdict

    from .security.sentinel import scan as sscan
    rep = sscan(Path(a.repo), a.commit)
    _out(asdict(rep))
    AuditLog().append("sentinel.scan", _actor(), {"repo": a.repo, "commit": a.commit,
                                                  "verdict": rep.verdict})
    return {"ELIGIBLE_FOR_SANDBOX": EXIT_OK, "QUARANTINE_FOR_REVIEW": EXIT_REVIEW}.get(
        rep.verdict, EXIT_BLOCKED)


def cmd_registry(a: argparse.Namespace) -> int:
    from .registry import CapabilityRegistry
    reg = CapabilityRegistry()
    if a.registry_cmd == "add":
        try:
            reg.add(a.kind, _load(a.file))
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return EXIT_BLOCKED
        AuditLog().append("registry.add", _actor(), {"kind": a.kind})
        _out({"added": True})
    else:
        probs = reg.problems()
        _out({"problems": probs})
        return EXIT_BLOCKED if probs else EXIT_OK
    return EXIT_OK


def cmd_jobs(a: argparse.Namespace) -> int:
    from dataclasses import asdict

    from .jobs import JobStore
    _out([asdict(j) for j in JobStore().all()])
    return EXIT_OK


def cmd_recover(a: argparse.Namespace) -> int:
    """Boot-time recovery sequence (spec §88)."""
    from .jobs import JobStore, recover
    from .registry import CapabilityRegistry
    steps: dict[str, Any] = {}
    ok, msg = AuditLog().verify()
    steps["audit"] = {"ok": ok, "detail": msg}
    try:
        reg = Registry.load()
        PolicyEngine.load(reg)
        steps["regulations"] = {"ok": True, "count": len(reg.regs)}
    except ValueError as e:
        steps["regulations"] = {"ok": False, "detail": str(e)}
    from .memory import MemoryLane
    mem_ok, mem_msg = MemoryLane().verify()
    steps["memory"] = {"ok": mem_ok, "detail": mem_msg}
    steps["capability_registry"] = {"problems": CapabilityRegistry().problems()}
    steps["credentials"] = {k: Path(v).exists() for k, v in {
        "audit_key": "/etc/bau/audit.key", "allowed_signers": "/etc/bau/allowed_signers",
        "unsubscribe_key": "/etc/bau/unsubscribe.key"}.items()}
    steps["jobs"] = recover(JobStore())
    AuditLog().append("system.recovered", "system:bau-recover",
                      {"audit_ok": ok, "jobs": len(steps["jobs"])})
    _out(steps)
    return EXIT_OK if ok and mem_ok and steps["regulations"]["ok"] else EXIT_BLOCKED


def cmd_hw(a: argparse.Namespace) -> int:
    paths = hardware.audit(Path(a.out))
    _out({k: str(v) for k, v in paths.items()})
    return EXIT_OK


def cmd_backup(a: argparse.Namespace) -> int:
    if a.backup_cmd == "manifest":
        doc = backup.manifest([Path(s) for s in a.sources], Path(a.out))
        _out({k: doc[k] for k in ("files", "bytes", "sensitive_paths", "unreadable")})
        return EXIT_OK
    res = backup.verify(Path(a.manifest), Path(a.backup_root),
                        Path(a.baseline_dir) / "BAU-BACKUP-BASELINE.json", a.encrypted)
    _out(res)
    return EXIT_OK if res["status"] == "VERIFIED" else EXIT_BLOCKED


def cmd_wipe_gate(a: argparse.Namespace) -> int:
    s = wipe_gate.evaluate(a.device, Path(a.baseline_dir), a.foundation, not a.lab_only,
                           Path(a.installer_record) if a.installer_record else None,
                           Path(a.recovery_plan) if a.recovery_plan else None)
    _out(s)
    if not s["ready"]:
        print("\nWIPE GATE NOT READY - nothing will be wiped.", file=sys.stderr)
        return EXIT_BLOCKED
    if not sys.stdin.isatty():
        print("wipe confirmation must be typed by a human at a terminal", file=sys.stderr)
        return EXIT_BLOCKED
    print(f"\nTARGET {s['target_device']}  MODEL {s['device_model']}  "
          f"SIZE {s['storage_bytes']} bytes", file=sys.stderr)
    serial = input("Type the disk SERIAL NUMBER exactly: ")
    phrase = input(f"Type 'WIPE {s['target_device']}' to confirm: ")
    try:
        rec = wipe_gate.confirm(s, serial, phrase, getpass.getuser())
    except PermissionError as e:
        print(str(e), file=sys.stderr)
        return EXIT_BLOCKED
    out = Path(a.baseline_dir) / "BAU-WIPE-GATE.json"
    out.write_text(json.dumps(rec, indent=2))
    _out({"gate_record": str(out), "expires_at": rec["expires_at"]})
    return EXIT_OK


def cmd_selftest(a: argparse.Namespace) -> int:
    """On-machine acceptance subset: everything that can be checked without a human."""
    import shutil
    results: dict[str, Any] = {}
    try:
        reg = Registry.load()
        PolicyEngine.load(reg)
        results["registry_and_policies"] = "ok"
    except ValueError as e:
        results["registry_and_policies"] = f"FAIL: {e}"
    results["audit_chain"] = "ok" if AuditLog().verify()[0] else "FAIL"
    from .memory import MemoryLane
    results["memory_chain"] = "ok" if MemoryLane().verify()[0] else "FAIL"
    container = os.environ.get("BAU_IN_CONTAINER") == "1"
    host_only = ("podman", "nft", "aa-status", "chronyc")   # the laptop's hardening layer
    for tool in (*host_only, "ssh-keygen", "ffmpeg"):
        results[f"tool:{tool}"] = "ok" if shutil.which(tool) else \
            "laptop only (not in the container)" if container and tool in host_only else "missing"
    for key, env in (("audit.key", "BAU_AUDIT_KEY"), ("unsubscribe.key", "BAU_UNSUB_KEY")):
        p = Path(os.environ.get(env) or Path("/etc/bau") / key)
        results[f"key:{key}"] = "ok" if p.exists() and (p.stat().st_mode & 0o007) == 0 \
            else "missing or world-readable"
    signers = _allowed_signers()
    results["approvers"] = "ok" if signers.exists() and signers.read_text().strip() \
        else f"no human approver registered ({signers})"
    _out(results)
    bad = [k for k, v in results.items() if v != "ok" and not v.startswith("laptop only")]
    return EXIT_OK if not bad else EXIT_REVIEW


# ---------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bau", description="BAU/BSA control plane")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create BAU_HOME and start the audit chain")
    s.add_argument("--home")
    s.add_argument("--refresh-data", action="store_true",
                   help="overwrite BAU_HOME regulations/policies with shipped defaults")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("status", help="Mission Control dashboard")
    s.add_argument("--brief", action="store_true")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("reg", help="regulation registry")
    rs = s.add_subparsers(dest="reg_cmd", required=True)
    rs.add_parser("validate")
    x = rs.add_parser("list")
    x.add_argument("--on")
    x = rs.add_parser("show")
    x.add_argument("reg_id")
    x = rs.add_parser("due")
    x.add_argument("--days", type=int, default=30)
    x.add_argument("--on")
    x = rs.add_parser("watch", help="hash official sources and flag changes for review")
    x.add_argument("--on")
    x = rs.add_parser("promote")
    x.add_argument("reg_id")
    x.add_argument("--to", required=True)
    x.add_argument("--reviewer", required=True)
    s.set_defaults(fn=cmd_reg)

    s = sub.add_parser("gate", help="evaluate a policy domain against a facts file")
    s.add_argument("domain")
    s.add_argument("--facts", required=True)
    s.add_argument("--scope")
    s.add_argument("--on")
    s.add_argument("--evidence", action="store_true")
    s.set_defaults(fn=cmd_gate)

    s = sub.add_parser("email", help="commercial email controls")
    es = s.add_subparsers(dest="email_cmd", required=True)
    x = es.add_parser("preflight")
    x.add_argument("--message", required=True)
    x.add_argument("--recipients", required=True)
    x.add_argument("--sender", required=True)
    x.add_argument("--evidence", action="store_true")
    x.add_argument("--approval", help="signed approval file from `bau approve`")
    x = es.add_parser("check-dns")
    x.add_argument("domain")
    x.add_argument("--selector", action="append")
    x = es.add_parser("headers")
    x.add_argument("url")
    x.add_argument("--mailto")
    x = es.add_parser("import-wireless-list")
    x.add_argument("file")
    x.add_argument("--fetched-at", required=True)
    x = es.add_parser("suppress")
    x.add_argument("address")
    x.add_argument("--reason", default="manual")
    x = es.add_parser("unsubscribe")
    x.add_argument("token")
    s.set_defaults(fn=cmd_email)

    s = sub.add_parser("sms", help="marketing text controls")
    ss = s.add_subparsers(dest="sms_cmd", required=True)
    x = ss.add_parser("preflight")
    x.add_argument("--message", required=True)
    x.add_argument("--recipient", required=True)
    x = ss.add_parser("inbound")
    x.add_argument("--number", required=True)
    x.add_argument("--text", required=True)
    s.set_defaults(fn=cmd_sms)

    s = sub.add_parser("consent", help="record a consent with evidence")
    s.add_argument("contact")
    s.add_argument("--channel", required=True, choices=["email", "sms", "voice"])
    s.add_argument("--purpose", default="marketing")
    s.add_argument("--basis", required=True)
    s.add_argument("--source", required=True)
    s.add_argument("--text-version", required=True)
    s.add_argument("--evidence-ref", required=True)
    s.add_argument("--jurisdiction", required=True)
    s.add_argument("--wireless-authorized", action="store_true")
    s.set_defaults(fn=cmd_consent)

    s = sub.add_parser("subscription", help="check a recurring offer")
    s.add_argument("offer")
    s.add_argument("--country")
    s.add_argument("--region")
    s.add_argument("--evidence", action="store_true")
    s.set_defaults(fn=cmd_subscription)

    s = sub.add_parser("disclosure", help="AI disclosure check before publishing")
    s.add_argument("artifact")
    s.add_argument("--context", required=True)
    s.set_defaults(fn=cmd_disclosure)

    s = sub.add_parser("monetize", help="IP monetization gate")
    s.add_argument("asset")
    s.add_argument("--market", default="US")
    s.add_argument("--evidence", action="store_true")
    s.set_defaults(fn=cmd_monetize)

    s = sub.add_parser("claims", help="scan marketing copy for risky claims")
    s.add_argument("file")
    s.set_defaults(fn=cmd_claims)

    s = sub.add_parser("tax", help="sales-tax nexus assessment")
    s.add_argument("jurisdiction")
    s.add_argument("--sales", required=True)
    s.add_argument("--transactions", type=int, required=True)
    s.add_argument("--physical-presence", choices=["yes", "no", "unknown"], default="unknown")
    s.add_argument("--marketplace-only", action="store_true")
    s.set_defaults(fn=cmd_tax)

    s = sub.add_parser("dsr", help="data-subject rights requests")
    ds = s.add_subparsers(dest="dsr_cmd", required=True)
    x = ds.add_parser("open")
    x.add_argument("subject")
    x.add_argument("--jurisdiction", action="append", required=True)
    x.add_argument("--rights", action="append", required=True)
    x = ds.add_parser("verify-identity")
    x.add_argument("request_id")
    x = ds.add_parser("store")
    x.add_argument("request_id")
    x.add_argument("store")
    x.add_argument("outcome")
    x.add_argument("--note")
    x = ds.add_parser("complete")
    x.add_argument("request_id")
    ds.add_parser("overdue")
    s.set_defaults(fn=cmd_dsr)

    s = sub.add_parser("audit", help="audit chain")
    au = s.add_subparsers(dest="audit_cmd", required=True)
    au.add_parser("verify")
    au.add_parser("anchor")
    x = au.add_parser("tail")
    x.add_argument("-n", type=int, default=20)
    s.set_defaults(fn=cmd_audit)

    s = sub.add_parser("secrets", help="scan files for embedded secrets")
    s.add_argument("path")
    s.set_defaults(fn=cmd_secrets)

    s = sub.add_parser("sentinel", help="static intake scan of a repository (never executes it)")
    s.add_argument("repo")
    s.add_argument("--commit")
    s.set_defaults(fn=cmd_sentinel)

    s = sub.add_parser("registry", help="capability registry")
    rg = s.add_subparsers(dest="registry_cmd", required=True)
    x = rg.add_parser("add")
    x.add_argument("kind")
    x.add_argument("file")
    rg.add_parser("validate")
    s.set_defaults(fn=cmd_registry)

    s = sub.add_parser("approve", help="sign an approval with YOUR ssh key (humans only)")
    s.add_argument("--capability", required=True)
    s.add_argument("--request-id", required=True)
    s.add_argument("--requester", required=True)
    s.add_argument("--minutes", type=int, default=60)
    s.add_argument("--scope", help="JSON limits, e.g. '{\"max_recipients\": 500}'")
    s.add_argument("--bind", required=True,
                   help="the exact file being approved (e.g. the message JSON)")
    s.add_argument("--evidence", help="evidence package to display before signing")
    s.add_argument("--key", default="~/.ssh/bau_approval_ed25519")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_approve)

    sub.add_parser("jobs", help="list jobs").set_defaults(fn=cmd_jobs)
    sub.add_parser("recover", help="boot-time recovery sequence").set_defaults(fn=cmd_recover)
    sub.add_parser("selftest", help="on-machine acceptance subset").set_defaults(fn=cmd_selftest)

    s = sub.add_parser("hw", help="read-only hardware audit")
    s.add_argument("action", choices=["audit"])
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_hw)

    s = sub.add_parser("backup", help="backup manifest and verification")
    bs = s.add_subparsers(dest="backup_cmd", required=True)
    x = bs.add_parser("manifest")
    x.add_argument("sources", nargs="+")
    x.add_argument("--out", required=True)
    x = bs.add_parser("verify")
    x.add_argument("--manifest", required=True)
    x.add_argument("--backup-root", required=True)
    x.add_argument("--baseline-dir", required=True)
    x.add_argument("--encrypted", action="store_true",
                   help="I confirm the backup medium is encrypted")
    s.set_defaults(fn=cmd_backup)

    s = sub.add_parser("wipe-gate", help="pre-wipe gate; requires typed confirmation")
    s.add_argument("--device", required=True)
    s.add_argument("--baseline-dir", required=True)
    s.add_argument("--foundation", default="debian", choices=sorted(wipe_gate.FOUNDATIONS))
    s.add_argument("--installer-record")
    s.add_argument("--recovery-plan")
    s.add_argument("--lab-only", action="store_true",
                   help="non-commercial lab install (permits noncommercial OS licences)")
    s.set_defaults(fn=cmd_wipe_gate)

    from .cli_ext import register
    register(sub)
    return p


def main(argv: list[str] | None = None) -> int:
    os.umask(0o007)  # state is shared by the bau group, never world-readable
    args = build_parser().parse_args(argv)
    try:
        return int(args.fn(args))
    except PermissionError as e:
        print(f"denied: {e}", file=sys.stderr)
        return EXIT_BLOCKED
    except (FileNotFoundError, json.JSONDecodeError, yaml.YAMLError, ValueError, KeyError,
            TypeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
