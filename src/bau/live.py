"""My Jarvis live USB: encrypted private storage (`jarvis-storage`).

The live system itself is read-only. Everything private (BAU state and keys, the owner's
home, saved Wi-Fi) lives in one LUKS2 container labelled `persistence`, which live-boot
opens at boot after asking for the passphrase (`persistence-encryption=lukslabel`: other
encrypted disks are never touched, unencrypted storage is never used). Only the folders
in PERSISTENCE_CONF persist; the rest of the system resets on every boot.

`jarvis-storage setup` creates that container either in the free space after the live
system on the boot USB, or on a separate disk that is completely empty. It never deletes
a partition: anything else is refused.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

LABEL = "persistence"            # LUKS2 label and filesystem label live-boot looks for
MAPPER = "jarvis-storage-setup"
MiB = 1 << 20
MIN_BYTES = 4 << 30              # the local model alone is 1.1 GB
LINUX_GPT = "0FC63DAF-8483-4772-8E79-3D69D8477DE4"
# Controlled persistence: only these survive a reboot; the system itself stays read-only.
PERSISTENCE_CONF = """\
/home union
/etc/bau bind
/var/lib/bau bind
/etc/NetworkManager/system-connections bind
"""


class StorageError(RuntimeError):
    pass


@dataclass
class Plan:
    disk: str
    start: int          # sectors
    size: int           # sectors
    sector: int         # bytes per sector
    label: str          # partition table: dos | gpt
    new_table: bool     # True only for a disk with no partitions at all

    @property
    def gib(self) -> float:
        return round(self.size * self.sector / (1 << 30), 1)

    def sfdisk_input(self) -> str:
        kind = LINUX_GPT if self.label == "gpt" else "83"
        line = f"start={self.start}, size={self.size}, type={kind}\n"
        return (f"label: {self.label}\n" if self.new_table else "") + line


def plan_free_space(disk: str, table: dict, disk_sectors: int, sector: int,
                    min_bytes: int = MIN_BYTES) -> Plan:
    """Room after the last partition (the live system) on the boot USB."""
    pt = table["partitiontable"]
    end = max((p["start"] + p["size"] for p in pt.get("partitions", [])), default=0)
    align = MiB // sector
    start = -(-end // align) * align
    last = disk_sectors
    if pt["label"] == "gpt":        # usable space ends where the GPT says (backup header after)
        last = min(int(pt.get("lastlba", disk_sectors - 34)) + 1, disk_sectors - 33)
    size = (last - start) // align * align
    if size * sector < min_bytes:
        raise StorageError(
            f"only {max(size, 0) * sector >> 20} MB free on {disk} after the live system; "
            f"need {min_bytes >> 30} GB. Use a bigger USB, or --device with an empty disk")
    return Plan(disk, start, size, sector, pt["label"], new_table=False)


def plan_empty_disk(disk: str, table: dict | None, disk_sectors: int, sector: int,
                    mounted: bool, min_bytes: int = MIN_BYTES) -> Plan:
    """A separate disk is used only when it holds no partitions at all."""
    if mounted:
        raise StorageError(f"{disk} is in use (mounted); refusing")
    if table and table["partitiontable"].get("partitions"):
        raise StorageError(f"{disk} already has partitions; jarvis-storage never deletes "
                           "data. Choose an empty disk")
    align = MiB // sector
    start = align
    size = (disk_sectors - 34 - start) // align * align
    if size * sector < min_bytes:
        raise StorageError(f"{disk} is smaller than {min_bytes >> 30} GB")
    return Plan(disk, start, size, sector, "gpt", new_table=True)


def needs_gpt_relocation(table: dict, disk_sectors: int) -> bool:
    """A disk image written to a bigger stick keeps its GPT backup header at the image's end."""
    pt = table["partitiontable"]
    return pt["label"] == "gpt" and int(pt.get("lastlba", disk_sectors - 34)) < disk_sectors - 34


# ------------------------------------------------------------------ system access

def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, text=True, **kw)


def _out(cmd: list[str]) -> str:
    return _run(cmd, capture_output=True).stdout.strip()


def boot_disk() -> str | None:
    """The whole disk the live system booted from, or None for a CD/DVD."""
    try:
        src = _out(["findmnt", "-no", "SOURCE", "/run/live/medium"])
        parent = _out(["lsblk", "-no", "PKNAME", src]).splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return f"/dev/{parent[0]}" if parent and parent[0] else None


def _table(disk: str) -> dict | None:
    r = subprocess.run(["sfdisk", "--json", disk], capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None


def _geometry(disk: str) -> tuple[int, int]:
    sector = int(_out(["blockdev", "--getss", disk]))
    return int(_out(["blockdev", "--getsize64", disk])) // sector, sector


def _mounted(disk: str) -> bool:
    rows = _out(["lsblk", "-rno", "MOUNTPOINTS", disk])
    return any(r.strip() for r in rows.splitlines())


def private_state() -> str:
    """encrypted | unencrypted | none: what is mounted as live persistence right now."""
    try:
        rows = _out(["findmnt", "-rno", "TARGET,SOURCE"]).splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "none"
    srcs = [r.split(" ", 1)[1] for r in rows
            if r.startswith("/run/live/persistence/") and " " in r]
    if not srcs:
        return "none"
    return "encrypted" if all(s.startswith("/dev/mapper/") for s in srcs) else "unencrypted"


def setup(device: str | None, passphrase_file: str | None, yes: bool) -> int:
    if device:
        table = _table(device)
        sectors, sector = _geometry(device)
        plan = plan_empty_disk(device, table, sectors, sector, _mounted(device))
    else:
        disk = boot_disk()
        if not disk:
            raise StorageError("the live system did not start from a USB disk (CD/DVD?): "
                               "use --device with an empty disk")
        table = _table(disk)
        if not table:
            raise StorageError(f"cannot read the partition table of {disk}")
        sectors, sector = _geometry(disk)
        if needs_gpt_relocation(table, sectors):
            # The image's GPT ends with the image; move its backup header to the real end
            # of the stick so the free space becomes usable. Existing partitions are kept.
            _run(["sfdisk", "--no-reread", "--no-tell-kernel", "--wipe", "never",
                  "--relocate", "gpt-bak-std", disk], capture_output=True)
            table = _table(disk) or table
        plan = plan_free_space(disk, table, sectors, sector)

    where = "the empty disk" if plan.new_table else "the free space on the My Jarvis USB"
    print(f"Encrypted private storage: {plan.gib} GB on {where} ({plan.disk}).\n"
          "Nothing that exists now is deleted. You choose a passphrase: without it the\n"
          "storage cannot be opened, by anyone. Write it down and keep it safe.")
    if not yes and input("Type YES to continue: ").strip() != "YES":
        print("Nothing changed.")
        return 1

    before = {p["node"] for p in ((table or {}).get("partitiontable", {})
                                   .get("partitions", []))}
    # --wipe never: the live system's own signatures on the stick must stay untouched.
    _run(["sfdisk", "--no-reread", "--no-tell-kernel", "--wipe", "never",
          "--wipe-partitions", "never"] + ([] if plan.new_table else ["--append"]) + [plan.disk],
         input=plan.sfdisk_input(), capture_output=True)
    after = _table(plan.disk) or {}
    new = [p for p in after["partitiontable"]["partitions"] if p["node"] not in before]
    if len(new) != 1:
        raise StorageError("could not find the new partition; nothing was encrypted")
    part = new[0]["node"]
    number = re.search(r"(\d+)$", part).group(1)
    # The boot USB is in use, so the kernel cannot re-read the whole table: add just this one.
    subprocess.run(["partx", "-a", "--nr", number, plan.disk], capture_output=True)
    _run(["udevadm", "settle"])

    key = ["--key-file", passphrase_file] if passphrase_file else []
    _run(["cryptsetup", "luksFormat", "--batch-mode", "--type", "luks2", "--label", LABEL,
          *([] if passphrase_file else ["--verify-passphrase"]), *key, part])
    _run(["cryptsetup", "open", *key, part, MAPPER])
    mnt = Path("/run") / MAPPER
    try:
        _run(["mkfs.ext4", "-q", "-L", LABEL, f"/dev/mapper/{MAPPER}"])
        mnt.mkdir(exist_ok=True)
        _run(["mount", f"/dev/mapper/{MAPPER}", str(mnt)])
        (mnt / "persistence.conf").write_text(PERSISTENCE_CONF)
        _run(["umount", str(mnt)])
    finally:
        subprocess.run(["cryptsetup", "close", MAPPER], capture_output=True)
    print(f"Done: {part} is encrypted. Restart the computer and choose 'My Jarvis'; "
          "type the passphrase when asked.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="jarvis-storage", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup", help="create the encrypted private storage (run once, as root)")
    s.add_argument("--device", help="an EMPTY disk to use instead of the boot USB's free space")
    s.add_argument("--passphrase-file", help="for automated tests only: read the passphrase "
                   "from this file instead of asking")
    s.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    sub.add_parser("status", help="is private storage unlocked and encrypted?")
    a = p.parse_args(argv)
    if a.cmd == "status":
        state = private_state()
        print({"encrypted": "PRIVATE: encrypted storage is unlocked",
               "unencrypted": "WARNING: unencrypted persistence is mounted",
               "none": "LIMITED: no private storage (nothing is saved)"}[state])
        return 0 if state == "encrypted" else 3
    try:
        return setup(a.device, a.passphrase_file, a.yes)
    except (StorageError, subprocess.CalledProcessError) as e:
        print(f"jarvis-storage: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
