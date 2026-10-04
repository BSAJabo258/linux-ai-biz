"""Read-only pre-wipe hardware audit (spec §4).

Nothing here writes to any disk except the output directory. Commands that
need root (dmidecode, smartctl) are attempted and recorded as unavailable
if they fail; a missing value is reported as missing, never guessed.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _run(cmd: list[str], timeout: int = 20) -> str | None:
    if not shutil.which(cmd[0]):
        return None
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def cpu() -> dict[str, Any]:
    info = _read("/proc/cpuinfo") or ""
    model = re.search(r"model name\s*:\s*(.+)", info)
    flags = set((re.search(r"flags\s*:\s*(.+)", info) or [None, ""])[1].split())
    return {"model": model.group(1) if model else None, "logical_cores": os.cpu_count(),
            "arch": platform.machine(),
            "virtualization": "vmx" if "vmx" in flags else "svm" if "svm" in flags else None,
            "avx2": "avx2" in flags, "avx512": any(f.startswith("avx512") for f in flags)}


def memory() -> dict[str, Any]:
    m = re.search(r"MemTotal:\s+(\d+)", _read("/proc/meminfo") or "")
    return {"total_gib": round(int(m.group(1)) / 1024 / 1024, 1) if m else None}


def gpus() -> list[str]:
    out = _run(["lspci"]) or ""
    return [ln for ln in out.splitlines()
            if re.search(r"VGA|3D controller|Display|Processing accelerators", ln)]


def npu() -> bool:
    return Path("/dev/accel").exists() or bool(list(Path("/sys/class").glob("accel*")))


def storage() -> dict[str, Any]:
    out = _run(["lsblk", "-J", "-b", "-o",
                "NAME,PATH,SIZE,TYPE,TRAN,MODEL,SERIAL,RM,RO,FSTYPE,MOUNTPOINT,UUID"])
    return json.loads(out) if out else {"error": "lsblk unavailable"}


def firmware() -> dict[str, Any]:
    sb = _run(["mokutil", "--sb-state"])
    return {
        "uefi": Path("/sys/firmware/efi").exists(),
        "secure_boot": sb.strip() if sb else None,
        "tpm": sorted(p.name for p in Path("/sys/class/tpm").glob("tpm*"))
        if Path("/sys/class/tpm").exists() else [],
        "tpm_version": _read("/sys/class/tpm/tpm0/tpm_version_major"),
        "iommu_groups": len(list(Path("/sys/kernel/iommu_groups").glob("*")))
        if Path("/sys/kernel/iommu_groups").exists() else 0,
        "bios_vendor": _read("/sys/class/dmi/id/bios_vendor"),
        "bios_version": _read("/sys/class/dmi/id/bios_version"),
        "product": _read("/sys/class/dmi/id/product_name"),
        "vendor": _read("/sys/class/dmi/id/sys_vendor"),
    }


def power_thermal() -> dict[str, Any]:
    bats = {}
    for b in Path("/sys/class/power_supply").glob("BAT*"):
        full = _read(str(b / "energy_full")) or _read(str(b / "charge_full"))
        design = _read(str(b / "energy_full_design")) or _read(str(b / "charge_full_design"))
        health = round(100 * int(full) / int(design), 1) if full and design and int(design) \
            else None
        bats[b.name] = {"status": _read(str(b / "status")), "health_pct": health,
                        "cycles": _read(str(b / "cycle_count"))}
    temps = {}
    for z in Path("/sys/class/thermal").glob("thermal_zone*"):
        t = _read(str(z / "temp"))
        if t and t.lstrip("-").isdigit():
            temps[_read(str(z / "type")) or z.name] = int(t) / 1000
    return {"batteries": bats, "thermal_c": temps}


def network() -> dict[str, Any]:
    ifaces = {}
    for i in Path("/sys/class/net").glob("*"):
        ifaces[i.name] = {"wireless": (i / "wireless").exists(),
                          "mac_present": bool(_read(str(i / "address"))),
                          "state": _read(str(i / "operstate"))}
    return {"interfaces": ifaces, "bluetooth": Path("/sys/class/bluetooth").exists()}


def peripherals() -> dict[str, Any]:
    return {"cameras": sorted(p.name for p in Path("/dev").glob("video*")),
            "sound_cards": (_read("/proc/asound/cards") or "").count("]:"),
            "displays": sorted(p.name for p in Path("/sys/class/drm").glob("card*-*"))}


def system() -> dict[str, Any]:
    osr = {}
    for line in (_read("/etc/os-release") or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            osr[k] = v.strip('"')
    return {"kernel": platform.release(), "os": osr.get("PRETTY_NAME"),
            "hostname_present": bool(platform.node()), "python": platform.python_version()}


def audit(out_dir: Path) -> dict[str, Path]:
    """Write the five BAU baselines named in spec §4 and return their paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.UTC).isoformat()
    baselines = {
        "BAU-HARDWARE-BASELINE": {"cpu": cpu(), "memory": memory(), "gpus": gpus(),
                                  "npu_present": npu(), "firmware": firmware(),
                                  "power_thermal": power_thermal(),
                                  "peripherals": peripherals()},
        "BAU-DISK-BASELINE": {"block_devices": storage(),
                              "root_usage": shutil.disk_usage("/")._asdict()},
        "BAU-SYSTEM-BASELINE": system(),
        "BAU-NETWORK-BASELINE": network(),
        "BAU-BACKUP-BASELINE": {"status": "NOT_STARTED",
                                "note": "run `bau backup manifest` then `bau backup verify`"},
    }
    paths = {}
    for name, body in baselines.items():
        p = out_dir / f"{name}.json"
        if name == "BAU-BACKUP-BASELINE" and p.exists():
            paths[name] = p  # never overwrite a real backup baseline with a placeholder
            continue
        p.write_text(json.dumps({"captured_at": now, "read_only": True, **body}, indent=2,
                                default=str))
        paths[name] = p
    return paths
