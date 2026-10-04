"""Secret scanner (spec §1.4). Used by Sentinel intake, CI and before any commit.

Findings report the location and kind only - never the secret value.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

PATTERNS = {
    "private_key": r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY( BLOCK)?-----",
    "aws_access_key": r"\b(AKIA|ASIA)[0-9A-Z]{16}\b",
    "github_token": r"\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{60,}\b",
    "slack_token": r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b",
    "stripe_key": r"\b(sk|rk)_live_[A-Za-z0-9]{20,}\b",
    "google_api_key": r"\bAIza[0-9A-Za-z_\-]{35}\b",
    "anthropic_key": r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b",
    "openai_key": r"\bsk-(proj-)?[A-Za-z0-9_\-]{32,}\b",
    "hf_token": r"\bhf_[A-Za-z0-9]{30,}\b",
    "jwt": r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
    "password_assignment": r"(?i)\b(password|passwd|secret|api_key|apikey|token)\s*[:=]\s*"
                           r"['\"][^'\"\s]{8,}['\"]",
}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache",
             ".ruff_cache", "dist", "build"}
SECRET_FILENAMES = {".env", "id_rsa", "id_ed25519", "id_ecdsa", ".netrc", ".pgpass",
                    "credentials", "credentials.json", "service-account.json"}
ALLOW_MARK = "bau:allow-secret-pattern"


def _entropy(s: str) -> float:
    if not s:
        return 0.0
    counts = {c: s.count(c) for c in set(s)}
    return -sum(n / len(s) * math.log2(n / len(s)) for n in counts.values())


def scan_text(text: str, where: str) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if ALLOW_MARK in line:
            continue
        for kind, rx in PATTERNS.items():
            for m in re.finditer(rx, line):
                if kind == "password_assignment" and _entropy(m.group(0)) < 3.0:
                    continue
                out.append({"file": where, "line": lineno, "kind": kind})
    return out


def scan_path(root: Path, max_bytes: int = 2_000_000) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    files = [root] if root.is_file() else root.rglob("*")
    for p in files:
        if any(part in SKIP_DIRS for part in p.parts) or not p.is_file():
            continue
        if p.name in SECRET_FILENAMES or p.suffix in (".pem", ".key", ".p12", ".pfx"):
            findings.append({"file": str(p), "line": 0, "kind": "secret_file"})
            continue
        try:
            if p.stat().st_size > max_bytes:
                continue
            data = p.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:4096]:
            continue
        findings.extend(scan_text(data.decode("utf-8", "replace"), str(p)))
    return findings
