"""Capability permissions, revocation and human approvals (spec §49, §55, §73).

Intelligence does not equal authority. An agent's request is authorized by
policy, not by the agent.

Two approval authorities share one interface (``sign`` / ``verify``):

* ``SshApprovals`` (production): each human approver signs with their OWN
  passphrase-protected SSH key (``ssh-keygen -Y sign``). The agent account can
  verify against ``/etc/bau/allowed_signers`` but holds no signing key, so it
  can never mint an approval, and every approval names the person who gave it.
* ``ApprovalAuthority`` (HMAC): for single-process use and tests. Whoever can
  verify can also sign, so it must never be readable by the agent account.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LEVELS = ["READ_ONLY", "LOW_RISK", "REVERSIBLE", "APPROVAL_REQUIRED", "HIGH_IMPACT", "CRITICAL"]
# Financial scale (spec §73) mapped onto the general scale so there is one ladder.
FINANCIAL = {"READ": "READ_ONLY", "PREPARE": "LOW_RISK", "RECOMMEND": "LOW_RISK",
             "REQUEST_APPROVAL": "APPROVAL_REQUIRED", "EXECUTE": "CRITICAL"}

DEFAULT_CAPABILITIES: dict[str, str] = {
    "github.read": "READ_ONLY",
    "github.write": "APPROVAL_REQUIRED",
    "email.send.commercial": "APPROVAL_REQUIRED",
    "sms.send.marketing": "HIGH_IMPACT",
    "publish.video": "APPROVAL_REQUIRED",
    "publish.text": "APPROVAL_REQUIRED",
    "delete.customer.data": "HIGH_IMPACT",
    "payment.read": "READ_ONLY",
    "payment.write": "CRITICAL",
    "move.money": "CRITICAL",
    "change.tax_configuration": "CRITICAL",
    "regulation.promote": "HIGH_IMPACT",
    "system.wipe": "CRITICAL",
}


class PermissionDenied(PermissionError):
    pass


@dataclass
class Approval:
    request_id: str
    capability: str
    requester: str
    approver: str
    approved_at: str
    expires_at: str
    scope: dict[str, Any]
    sig: str = ""

    def payload(self) -> bytes:
        d = {k: v for k, v in self.__dict__.items() if k != "sig"}
        return json.dumps(d, sort_keys=True).encode()


class ApprovalAuthority:
    def __init__(self, key: bytes):
        if len(key) < 32:
            raise ValueError("approval key must be at least 32 bytes")
        self.key = key

    def sign(self, a: Approval, require_tty: bool = True) -> Approval:
        if a.approver == a.requester:
            raise PermissionDenied("separation of duties: requester cannot approve")
        if a.approver.startswith(("agent:", "model:", "bau-")):
            raise PermissionDenied("approvals must come from a human identity")
        if require_tty and not sys.stdin.isatty():
            raise PermissionDenied("approval must be given interactively by a human")
        a.sig = hmac.new(self.key, a.payload(), hashlib.sha256).hexdigest()
        return a

    def verify(self, a: Approval, capability: str, now: dt.datetime | None = None) -> bool:
        now = now or dt.datetime.now(dt.UTC)
        good = hmac.new(self.key, a.payload(), hashlib.sha256).hexdigest()
        return (hmac.compare_digest(a.sig, good) and a.capability == capability
                and dt.datetime.fromisoformat(a.expires_at) > now)


NAMESPACE = "bau-approval"


class SshApprovals:
    def __init__(self, allowed_signers: Path = Path("/etc/bau/allowed_signers")):
        self.allowed_signers = allowed_signers
        self.tool = shutil.which("ssh-keygen")
        if not self.tool:
            raise RuntimeError("ssh-keygen (openssh-client) is required for approvals")

    @staticmethod
    def principal(approver: str) -> str:
        if not approver.startswith("human:"):
            raise PermissionDenied("approvals must come from a human identity")
        return approver.split(":", 1)[1]

    def sign(self, a: Approval, key_path: Path, require_tty: bool = True) -> Approval:
        if a.approver == a.requester:
            raise PermissionDenied("separation of duties: requester cannot approve")
        self.principal(a.approver)
        if require_tty and not sys.stdin.isatty():
            raise PermissionDenied("approval must be given interactively by a human")
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / "approval"
            data.write_bytes(a.payload())
            # ssh-keygen prompts for the key passphrase on the terminal.
            subprocess.run([self.tool, "-Y", "sign", "-q", "-f", str(key_path), "-n",
                            NAMESPACE, str(data)], check=True)
            a.sig = (Path(td) / "approval.sig").read_text()
        return a

    def verify(self, a: Approval, capability: str, now: dt.datetime | None = None) -> bool:
        now = now or dt.datetime.now(dt.UTC)
        if a.capability != capability or dt.datetime.fromisoformat(a.expires_at) <= now:
            return False
        if a.approver == a.requester or not a.sig:
            return False
        try:
            principal = self.principal(a.approver)
        except PermissionDenied:
            return False
        with tempfile.TemporaryDirectory() as td:
            sig = Path(td) / "approval.sig"
            sig.write_text(a.sig)
            r = subprocess.run([self.tool, "-Y", "verify", "-f", str(self.allowed_signers),
                                "-I", principal, "-n", NAMESPACE, "-s", str(sig)],
                               input=a.payload(), capture_output=True, check=False)
        return r.returncode == 0


def load_approval(path: Path) -> Approval:
    return Approval(**json.loads(path.read_text()))


@dataclass
class CapabilityTable:
    levels: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_CAPABILITIES))
    revoked: set[str] = field(default_factory=set)
    agent_ceiling: dict[str, str] = field(default_factory=dict)  # agent -> max level

    def revoke(self, capability: str) -> None:
        self.revoked.add(capability)

    def restore(self, capability: str) -> None:
        self.revoked.discard(capability)

    def authorize(self, agent: str, capability: str, approval: Approval | None = None,
                  authority: ApprovalAuthority | SshApprovals | None = None) -> str:
        if capability in self.revoked:
            raise PermissionDenied(f"{capability} is revoked")
        level = self.levels.get(capability)
        if level is None:
            raise PermissionDenied(f"{capability} is not a registered capability")
        ceiling = self.agent_ceiling.get(agent, "LOW_RISK")
        needs_approval = LEVELS.index(level) >= LEVELS.index("APPROVAL_REQUIRED")
        if LEVELS.index(level) > LEVELS.index(ceiling) and not needs_approval:
            raise PermissionDenied(f"{agent} ceiling {ceiling} < {level}")
        if needs_approval:
            if approval is None or authority is None:
                raise PermissionDenied(f"{capability} ({level}) requires human approval")
            if approval.requester != agent:
                raise PermissionDenied("approval was issued for a different requester")
            if not authority.verify(approval, capability):
                raise PermissionDenied("approval invalid, expired, or for another capability")
        return level
