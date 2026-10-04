"""MAYA Sentinel: repository intake gate (spec §1.3, §36-37, §111-112).

Spec §1.3 and §37 listed the intake steps in two different orders; this is
the single canonical order. Static analysis only: Sentinel NEVER runs
`pip install`, `npm install`, build scripts or tests of an untrusted repo.
Those happen later, inside the sandbox stage, after a human has approved.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .secrets_scan import scan_path

STATES = ["DISCOVERED", "UNTRUSTED", "SENTINEL_SCANNED", "LICENSE_REVIEWED",
          "PROVENANCE_REVIEWED", "SBOM_REVIEWED", "SECURITY_REVIEWED", "QUARANTINED",
          "SANDBOX_TESTED", "BENCHMARKED", "COMPLIANCE_REVIEWED", "REGISTERED", "APPROVED",
          "ACTIVE"]
TERMINAL_BAD = {"REJECTED", "REVOKED"}

# SPDX ids with clear commercial use. Anything else needs human license review.
COMMERCIAL_OK = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "MPL-2.0",
                 "Zlib", "Unlicense", "0BSD", "CC0-1.0", "PSF-2.0"}
COPYLEFT = {"GPL-2.0", "GPL-3.0", "LGPL-2.1", "LGPL-3.0", "AGPL-3.0"}
NONCOMMERCIAL = {"PolyForm-Noncommercial-1.0.0", "CC-BY-NC-4.0", "CC-BY-NC-SA-4.0",
                 "BUSL-1.1", "SSPL-1.0", "Elastic-2.0", "Commons-Clause"}

LICENSE_HINTS = [
    ("PolyForm-Noncommercial-1.0.0", r"PolyForm Noncommercial"),
    ("BUSL-1.1", r"Business Source License"),
    ("SSPL-1.0", r"Server Side Public License"),
    ("Elastic-2.0", r"Elastic License 2\.0"),
    ("Commons-Clause", r"Commons Clause"),
    ("CC-BY-NC-4.0", r"Attribution-NonCommercial"),
    ("AGPL-3.0", r"GNU AFFERO GENERAL PUBLIC LICENSE"),
    ("LGPL-3.0", r"GNU LESSER GENERAL PUBLIC LICENSE\s+Version 3"),
    ("LGPL-2.1", r"GNU LESSER GENERAL PUBLIC LICENSE\s+Version 2\.1"),
    ("GPL-3.0", r"GNU GENERAL PUBLIC LICENSE\s+Version 3"),
    ("GPL-2.0", r"GNU GENERAL PUBLIC LICENSE\s+Version 2"),
    ("Apache-2.0", r"Apache License,?\s+Version 2\.0"),
    ("MPL-2.0", r"Mozilla Public License,?\s+(Version|v\.?)\s*2\.0"),
    ("MIT", r"\bMIT License\b|Permission is hereby granted, free of charge"),
    ("BSD-3-Clause", r"Neither the name of"),
    ("BSD-2-Clause", r"Redistribution and use in source and binary forms"),
    ("ISC", r"\bISC License\b"),
    ("Unlicense", r"This is free and unencumbered software"),
]

RISKY_CODE = {
    "pipe_to_shell": r"(curl|wget)[^\n|]*\|\s*(sudo\s+)?(ba|z)?sh\b",
    "base64_exec": r"(base64\s+(-d|--decode)[^\n]*\|\s*(ba)?sh)|exec\(\s*base64",
    "python_eval_remote": r"(eval|exec)\(\s*(requests|urllib)",
    "obfuscated_js": r"eval\(\s*(atob|Function)\(",
    "persistence": r"crontab\s+-|/etc/systemd/system|\.bashrc|LaunchAgents|/etc/rc\.local",
    "ssh_key_access": r"\.ssh/(id_|authorized_keys)",
    "browser_cookie_access": r"Cookies(\.sqlite)?|Login Data|cookies\.sqlite",
    "wallet_access": r"wallet\.dat|\.electrum|metamask",
    "disable_security": r"setenforce 0|aa-teardown|ufw disable|iptables -F",
}


def detect_license(repo: Path) -> dict[str, Any]:
    cands = [p for p in repo.iterdir() if p.is_file() and re.match(
        r"(?i)^(licen[cs]e|copying|notice)(\.|$)", p.name)]
    found = []
    for p in cands:
        text = p.read_text(errors="replace")[:20000]
        for spdx, rx in LICENSE_HINTS:
            if re.search(rx, text, re.IGNORECASE):
                found.append(spdx)
                break
    for meta, key in (("package.json", "license"),):
        mp = repo / meta
        if mp.exists():
            try:
                lic = json.loads(mp.read_text()).get(key)
                if isinstance(lic, str):
                    found.append(lic)
            except json.JSONDecodeError:
                pass
    found = sorted(set(found))
    if not found:
        verdict = "UNKNOWN_LICENSE"
    elif any(f in NONCOMMERCIAL for f in found):
        verdict = "NONCOMMERCIAL_BLOCK"
    elif any(f in COPYLEFT for f in found):
        verdict = "COPYLEFT_REVIEW"
    elif all(f in COMMERCIAL_OK for f in found):
        verdict = "COMMERCIAL_OK"
    else:
        verdict = "HUMAN_REVIEW"
    return {"files": [p.name for p in cands], "detected": found, "verdict": verdict}


def install_hooks(repo: Path) -> list[dict[str, str]]:
    hooks = []
    pj = repo / "package.json"
    if pj.exists():
        try:
            scripts = json.loads(pj.read_text()).get("scripts", {}) or {}
        except json.JSONDecodeError:
            scripts = {}
        for k in ("preinstall", "install", "postinstall", "prepare"):
            if k in scripts:
                hooks.append({"file": "package.json", "hook": k, "cmd": str(scripts[k])[:200]})
    if (repo / "setup.py").exists():
        hooks.append({"file": "setup.py", "hook": "setup.py executes arbitrary code at install",
                      "cmd": ""})
    for name in ("install.sh", "Makefile", "build.rs"):
        if (repo / name).exists():
            hooks.append({"file": name, "hook": "build/install script", "cmd": ""})
    return hooks


def surfaces(repo: Path) -> dict[str, bool]:
    names = " ".join(str(p.relative_to(repo)).lower() for p in repo.rglob("*")
                     if ".git" not in p.parts)
    return {"mcp_server": "mcp" in names,
            "agent_framework": any(w in names for w in ("agent", "autogen", "crew")),
            "dockerfile": "dockerfile" in names,
            "github_actions": ".github/workflows" in names,
            "binaries": any(p.suffix in (".exe", ".dll", ".so", ".dylib", ".bin")
                            for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts)}


def risky_code(repo: Path, limit: int = 200) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in repo.rglob("*"):
        if not p.is_file() or ".git" in p.parts or p.stat().st_size > 1_000_000:
            continue
        if p.suffix not in (".sh", ".py", ".js", ".ts", ".mjs", ".cjs", ".ps1", ".rb", "",
                            ".yml", ".yaml", ".toml", ".json", ".bash"):
            continue
        text = p.read_text(errors="replace")
        for kind, rx in RISKY_CODE.items():
            if re.search(rx, text, re.IGNORECASE):
                out.append({"file": str(p.relative_to(repo)), "kind": kind})
                if len(out) >= limit:
                    return out
    return out


@dataclass
class IntakeReport:
    repo: str
    commit: str | None
    license: dict[str, Any]
    install_hooks: list[dict[str, str]]
    risky_code: list[dict[str, Any]]
    secrets: list[dict[str, object]]
    surfaces: dict[str, bool]
    verdict: str = ""
    reasons: list[str] = field(default_factory=list)

    def decide(self) -> None:
        r = []
        if self.license["verdict"] in ("NONCOMMERCIAL_BLOCK", "UNKNOWN_LICENSE"):
            r.append(f"license: {self.license['verdict']}")
        if self.secrets:
            r.append(f"{len(self.secrets)} embedded secret(s)")
        bad = {f["kind"] for f in self.risky_code}
        if bad & {"pipe_to_shell", "base64_exec", "python_eval_remote", "obfuscated_js",
                  "wallet_access", "browser_cookie_access", "disable_security"}:
            r.append(f"dangerous code patterns: {sorted(bad)}")
        self.reasons = r
        if r:
            self.verdict = "REJECT_OR_HUMAN_REVIEW"
        elif self.install_hooks or self.surfaces.get("binaries") or self.license["verdict"] != \
                "COMMERCIAL_OK":
            self.verdict = "QUARANTINE_FOR_REVIEW"
        else:
            self.verdict = "ELIGIBLE_FOR_SANDBOX"


def scan(repo: Path, commit: str | None = None) -> IntakeReport:
    rep = IntakeReport(repo=str(repo), commit=commit, license=detect_license(repo),
                       install_hooks=install_hooks(repo), risky_code=risky_code(repo),
                       secrets=scan_path(repo), surfaces=surfaces(repo))
    rep.decide()
    return rep


def advance(current: str, to: str) -> str:
    if to in TERMINAL_BAD:
        return to
    if current in TERMINAL_BAD:
        raise ValueError(f"{current} is terminal")
    if STATES.index(to) != STATES.index(current) + 1:
        raise ValueError(f"intake cannot skip from {current} to {to}")
    return to
