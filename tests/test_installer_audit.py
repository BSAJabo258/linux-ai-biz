"""Every audit record install.sh writes must pass the audit chain's PII guard.

Regression: the VM test run (2026-10-05) found install.sh passing the whole
payload MANIFEST (which has a "name" key) to the audit chain; the guard
refused it and the installer died on its last step.
"""
import json
import re
import subprocess
from pathlib import Path

from bau.audit import AuditLog

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "installer" / "payload" / "install.sh"


def test_static_audit_records_pass_pii_guard(tmp_path):
    text = INSTALL.read_text()
    log = AuditLog(tmp_path / "a.jsonl", key=b"")
    found = 0
    for event, raw in re.findall(r"^\s*audit (\S+) '(\{.*\})'\s*$", text, re.M):
        log.append(event, "installer", json.loads(raw))
        found += 1
    gated = re.search(r'audit install\.gated "(.*)"', text).group(1)
    log.append("install.gated", "installer",
               json.loads(gated.replace('\\"', '"').replace("${h}", "0" * 64)))
    assert found >= 1


def test_manifest_summary_passes_pii_guard(tmp_path):
    text = INSTALL.read_text()
    snippet = re.search(r"python3 -c '(import json,sys;.*?)' \\\n", text, re.S).group(1)
    manifest = tmp_path / "MANIFEST.json"
    manifest.write_text(json.dumps({"name": "BAU-PAYLOAD", "version": "0.3.0",
                                    "git_commit": "abc", "git_dirty": False,
                                    "built_at": "2026-10-05T00:00:00Z",
                                    "target": "Debian 13+ amd64"}))
    out = subprocess.run(["python3", "-c", snippet, str(manifest)], capture_output=True,
                         text=True, check=True).stdout
    data = json.loads(out)
    assert "name" not in data and data["payload_version"] == "0.3.0"
    AuditLog(tmp_path / "a.jsonl", key=b"").append("install.completed", "installer", data)


def test_install_sh_packages_are_all_preinstalled_by_usb1():
    """USB #2 must work offline on a fresh USB #1 install: every package install.sh
    requires has to be in the preseed's pkgsel list (or Debian's standard set), and
    must be a real package name - `dpkg -s` never succeeds for virtual ones.
    Regression: Debian 13 made `dnsutils` virtual (bind9-dnsutils), so every
    install tried to download it and --offline always failed."""
    sh = INSTALL.read_text()
    required = re.search(r"pkgs=\(([^)]*)\)", sh).group(1).split()
    preseed = (ROOT / "installer" / "preseed" / "bau.preseed").read_text()
    include = re.search(r"pkgsel/include string (.*?)\n(?!\s)", preseed, re.S).group(1)
    preinstalled = set(include.replace("\\", " ").split())
    standard = {"python3"}            # in Debian's standard task as well
    missing = [p for p in required if p not in preinstalled | standard]
    assert not missing, f"install.sh needs packages USB #1 does not install: {missing}"
    virtual_in_debian13 = {"dnsutils"}
    assert not (set(required) | preinstalled) & virtual_in_debian13


def test_upgrade_restarts_long_running_services():
    """Regression (VM run): re-running install.sh left Mission Control serving the old
    code until reboot because the long-running service was only `start`ed."""
    sh = INSTALL.read_text()
    long_running = [p.name for p in (ROOT / "installer" / "payload" / "systemd").glob(
        "*.service") if "Type=oneshot" not in p.read_text()
        and f"{p.name}" in sh.split("# ---------------------------------------------------"
                                    "------------- 7. services")[1]]
    assert long_running, "expected at least one long-running service"
    for svc in long_running:
        assert re.search(rf"systemctl (try-)?restart [^\n]*{re.escape(svc)}", sh), svc
