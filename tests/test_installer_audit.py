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
