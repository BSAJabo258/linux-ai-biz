"""The graphics card watchdog (installer/bau-gpu-watch.sh, docs/GPU.md): the desktop's card fell
off the PCI Express bus (Xid 79) at the end of four boots in a row, 2026-11-19 to 2026-11-21,
and everything on it stayed dead until a person restarted. Run with stand-in commands: nothing
here restarts anything."""

import os
import subprocess
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "installer" / "bau-gpu-watch.sh"
FELL = ("NVRM: Xid (PCI:0000:05:00): 79, pid='<unknown>', name=<unknown>, GPU has fallen off "
        "the bus.")


def crash(line):
    return subprocess.run(["bash", str(SCRIPT), "--is-crash", line]).returncode == 0


def test_only_the_card_falling_off_the_bus_counts():
    assert crash(FELL)
    assert crash("NVRM: GPU 0000:05:00.0: GPU has fallen off the bus.")
    assert not crash("NVRM: Xid (PCI:0000:05:00): 13, Graphics Exception")
    assert not crash("NVRM: Xid (PCI:0000:05:00): 179, something else")
    assert not crash("nvidia-modeset: ERROR: GPU:0: Failed to query display engine channel")


def watch(tmp_path, restarts=()):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    did = tmp_path / "did"
    fakes = {"journalctl": f"printf '%s\\n' \"{FELL}\"",
             "nvidia-bug-report.sh": f"echo report >> {did}",
             "logger": f"echo \"logger $*\" >> {did}",
             "sleep": "true",
             "systemctl": f"echo \"systemctl $*\" >> {did}"}
    for name, body in fakes.items():
        (bin_ / name).write_text(f"#!/bin/sh\n{body}\n")
        (bin_ / name).chmod(0o755)
    log = tmp_path / "log"
    log.mkdir()
    if restarts:
        (log / "restarts").write_text("".join(f"{int(t)}\n" for t in restarts))
    env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "BAU_GPU_LOG": str(log)}
    subprocess.run(["bash", str(SCRIPT), "--watch"], env=env, check=True, timeout=30)
    return (did.read_text() if did.exists() else ""), log


def test_a_crash_saves_nvidias_report_then_restarts(tmp_path):
    did, log = watch(tmp_path)
    assert did.index("report") < did.index("systemctl reboot")    # the report first
    assert "fell off the bus" in did
    assert FELL in (log / "crashes").read_text()
    assert len((log / "restarts").read_text().split()) == 1


def test_it_never_restarts_more_than_three_times_in_six_hours(tmp_path):
    now = time.time()
    did, log = watch(tmp_path, restarts=(now - 600, now - 1200, now - 1800))
    assert "systemctl reboot" not in did and "not restarting" in did
    assert "report" in did                                          # still recorded


def test_old_restarts_do_not_count(tmp_path):
    old = time.time() - 7 * 3600
    did, _ = watch(tmp_path, restarts=(old, old, old))
    assert "systemctl reboot" in did
