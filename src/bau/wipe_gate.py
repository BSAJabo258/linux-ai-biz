"""Destructive wipe gate (spec §5).

A previous plan authorizing a wipe is not authorization. Immediately before
the wipe this gate shows the target, re-checks every precondition from the
saved baselines, and requires a human to type the disk's serial number.
It produces a short-lived gate record that the installer imports into the
new system's audit chain; an install without one is marked UNGATED.

Note the gate cannot itself stop someone from booting the installer: the
Debian installer's partitioner asks for its own confirmation. This gate
makes sure that confirmation is given knowingly and is recorded.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

FOUNDATIONS = {
    # foundation -> (license, commercial use allowed)
    "debian": ("DFSG-free (Debian Social Contract)", True),
    "aios": ("PolyForm Noncommercial 1.0.0", False),
}
MAX_BASELINE_AGE = dt.timedelta(days=7)


def _load(p: Path) -> dict[str, Any] | None:
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _fresh(doc: dict[str, Any] | None, now: dt.datetime) -> bool:
    if not doc or "captured_at" not in doc:
        return False
    return now - dt.datetime.fromisoformat(doc["captured_at"]) <= MAX_BASELINE_AGE


def _find_device(disk: dict[str, Any], device: str) -> dict[str, Any] | None:
    for d in (disk or {}).get("block_devices", {}).get("blockdevices", []):
        if d.get("path") == device or f"/dev/{d.get('name')}" == device:
            return d
    return None


def k3_mode(hw: dict[str, Any] | None, min_ram_gib: float) -> str:
    ram = ((hw or {}).get("memory") or {}).get("total_gib")
    if ram is None:
        return "UNDETERMINED"
    return "LOCAL_CANDIDATE (benchmark before relying on it)" if ram >= min_ram_gib \
        else "OFFLOAD/REMOTE/EMERGENCY - local hardware insufficient (spec §6)"


def evaluate(device: str, baseline_dir: Path, foundation: str, commercial: bool,
             installer_record: Path | None, recovery_plan: Path | None,
             k3_min_ram_gib: float = 512.0, now: dt.datetime | None = None
             ) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.UTC)
    hw = _load(baseline_dir / "BAU-HARDWARE-BASELINE.json")
    disk = _load(baseline_dir / "BAU-DISK-BASELINE.json")
    bk = _load(baseline_dir / "BAU-BACKUP-BASELINE.json")
    inst = _load(installer_record) if installer_record else None
    dev = _find_device(disk or {}, device)
    lic, commercial_ok = FOUNDATIONS.get(foundation, ("UNKNOWN", False))
    checks = {
        "hardware_baseline_fresh": _fresh(hw, now),
        "disk_baseline_fresh": _fresh(disk, now),
        "target_device_found": dev is not None,
        # lsblk reports rm as true/false or "1"/"0" depending on util-linux version
        "target_not_removable": bool(dev) and (dev or {}).get("rm") not in (True, 1, "1"),
        "backup_verified": bool(bk) and bk.get("status") == "VERIFIED" and _fresh(bk, now),
        "installer_media_verified": bool(inst) and inst.get("verified") is True,
        "golden_recovery_plan_present": bool(recovery_plan and recovery_plan.is_file()),
        "os_license_verified": foundation in FOUNDATIONS,
        "os_license_permits_use": commercial_ok or not commercial,
    }
    return {
        "target_device": device,
        "device_model": (dev or {}).get("model"),
        "device_serial": (dev or {}).get("serial"),
        "storage_bytes": (dev or {}).get("size"),
        "foundation": foundation, "os_license": lic, "commercial_deployment": commercial,
        "k3_deployment_mode": k3_mode(hw, k3_min_ram_gib),
        "checks": checks,
        "ready": all(checks.values()),
    }


def confirm(summary: dict[str, Any], typed_serial: str, typed_phrase: str,
            operator: str, ttl_minutes: int = 60) -> dict[str, Any]:
    if not summary["ready"]:
        failed = [k for k, v in summary["checks"].items() if not v]
        raise PermissionError(f"wipe gate not ready: {failed}")
    serial = summary.get("device_serial") or ""
    if not serial or typed_serial.strip() != serial:
        raise PermissionError("typed serial does not match the target disk")
    if typed_phrase.strip() != f"WIPE {summary['target_device']}":
        raise PermissionError("confirmation phrase mismatch")
    now = dt.datetime.now(dt.UTC)
    rec = dict(summary, operator=operator, confirmed_at=now.isoformat(),
               expires_at=(now + dt.timedelta(minutes=ttl_minutes)).isoformat())
    rec["record_hash"] = hashlib.sha256(json.dumps(rec, sort_keys=True).encode()).hexdigest()
    return rec
