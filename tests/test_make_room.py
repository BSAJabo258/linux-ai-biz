"""Make room for Jarvis (installer/bau-make-room.sh; the owner's problem, 2026-11-08: "/" fills up
while /home stays nearly empty). The real script runs here against fake disk commands: the big
folders are copied to /home/bau-data, checked, linked back with a bind line in fstab, and the old
copy removed. Nothing on this computer is changed."""

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "installer" / "bau-make-room.sh"


def box(tmp: Path, crypt=True, home_free=500 << 30, active=("bau-llm.service",)):
    r = tmp / "root"
    models = r / "var/lib/bau/models"
    models.mkdir(parents=True)
    (models / "qwen.gguf").write_bytes(b"m" * 4096)
    (r / "usr/local/comfyui/ComfyUI").mkdir(parents=True)
    (r / "usr/local/comfyui/ComfyUI/main.py").write_text("print()")
    (r / "var/lib/bau/audit").mkdir(parents=True)              # must never move
    (r / "var/lib/bau/audit/chain.jsonl").write_text("{}")
    (r / "home").mkdir()
    (r / "etc").mkdir()
    (r / "etc/fstab").write_text("UUID=x / ext4 defaults 0 1\n")
    state = tmp / "state"
    state.mkdir()
    bin_ = tmp / "bin"
    bin_.mkdir()
    cmds = {
        "id": "echo 0",
        "systemctl": f'''case "$1" in
  is-active) for a in {" ".join(active)}; do [ "$a" = "$3" ] && exit 0; done; exit 3 ;;
  *) echo "$*" >> {state}/systemctl ;;
esac''',
        # df: anything under /home is the big encrypted part, the rest is "/"
        "df": f'''last=""; for a in "$@"; do last="$a"; done
case "$*" in
  *--output=avail*) echo Avail
    case "$last" in */home|*/home/*) echo {home_free} ;; *) echo 1000 ;; esac ;;
  *--output=target*) echo Mounted
    case "$last" in */home|*/home/*) echo /home ;; *) echo / ;; esac ;;
  *) echo "Filesystem Size Used Avail" ;;
esac''',
        "findmnt": "echo /dev/mapper/bau--vg-home",
        "lsblk": "echo lvm; echo crypt" if crypt else "echo lvm; echo part",
        "mount": f'echo "$3" >> {state}/mounts',
        "umount": f'grep -vx "$1" {state}/mounts > {state}/m2; mv {state}/m2 {state}/mounts',
        "mountpoint": f'[ -f {state}/mounts ] && grep -qx "$2" {state}/mounts',
    }
    for name, body in cmds.items():
        p = bin_ / name
        p.write_text("#!/bin/sh\n" + body + "\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    env = {**os.environ, "PATH": f"{bin_}:/usr/bin:/bin", "BAU_ROOM_ROOT": str(r),
           "BAU_ROOM_FSTAB": str(r / "etc/fstab")}
    return env, r, state


def run(env, *args):
    return subprocess.run(["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True,
                          timeout=60)


def test_big_folders_move_to_home_and_link_back_and_nothing_else_moves(tmp_path):
    env, r, state = box(tmp_path)
    out = run(env)
    assert out.returncode == 0, out.stdout + out.stderr
    data = r / "home/bau-data"
    assert (data / "_var_lib_bau_models/qwen.gguf").read_bytes() == b"m" * 4096
    assert (data / "_usr_local_comfyui/ComfyUI/main.py").exists()
    fstab = (r / "etc/fstab").read_text()
    assert f"{data}/_var_lib_bau_models {r}/var/lib/bau/models none bind 0 0" in fstab
    assert not (r / "var/lib/bau/models.bau-old").exists()        # the old copy freed the space
    assert (r / "var/lib/bau/audit/chain.jsonl").exists()          # keys, data, audit stay put
    assert not (data / "_var_lib_bau_audit").exists()
    calls = (state / "systemctl").read_text()
    assert "stop bau-llm.service" in calls and "start bau-llm.service" in calls
    assert "Moved 2 folder(s)" in out.stdout
    again = run(env)                                                 # safe to run twice
    assert "Already moved" in again.stdout and fstab == (r / "etc/fstab").read_text()


def test_it_refuses_a_target_that_frees_nothing_or_is_not_encrypted(tmp_path):
    env, r, _ = box(tmp_path)
    same = run(env, str(r / "srv/bau"))                              # on "/": frees nothing
    assert same.returncode == 1 and "frees nothing" in same.stdout
    env2, r2, _ = box(tmp_path / "b", crypt=False)
    plain = run(env2)
    assert plain.returncode == 1 and "not on an encrypted disk" in plain.stdout
    assert (r2 / "var/lib/bau/models/qwen.gguf").exists()           # nothing moved


def test_not_enough_room_skips_and_keeps_the_folder(tmp_path):
    env, r, _ = box(tmp_path, home_free=10)
    out = run(env)
    assert "Not enough room" in out.stdout
    assert (r / "var/lib/bau/models/qwen.gguf").exists()
    assert "bind" not in (r / "etc/fstab").read_text()


def test_undo_brings_it_back_when_there_is_room(tmp_path):
    env, r, state = box(tmp_path)
    run(env)
    env["PATH"] = env["PATH"]                                        # same fakes; "/" has room
    (tmp_path / "bin/df").write_text("#!/bin/sh\n" + '''last=""; for a in "$@"; do last="$a"; done
case "$*" in
  *--output=avail*) echo Avail; echo 999999999999 ;;
  *--output=target*) echo Mounted
    case "$last" in */home|*/home/*) echo /home ;; *) echo / ;; esac ;;
  *) echo "Filesystem Size Used Avail" ;;
esac
''')
    out = run(env, "--undo")
    assert out.returncode == 0, out.stdout + out.stderr
    assert (r / "var/lib/bau/models/qwen.gguf").read_bytes() == b"m" * 4096
    assert "bind" not in (r / "etc/fstab").read_text()


def test_the_setup_card_copy_is_the_installers_own():
    assert (ROOT / "src/bau/data/setup/bau-make-room.sh").read_text() == SCRIPT.read_text()


def test_new_installs_use_one_partition_so_this_cannot_happen_again():
    for f in ("image/live-build/config/includes.installer/preseed.cfg",
              "installer/preseed/bau.preseed"):
        text = (ROOT / f).read_text()
        assert "d-i partman-auto/choose_recipe select atomic" in text, f
        assert "choose_recipe select home" not in text, f
        assert "d-i partman-auto/method string crypto" in text, f        # still encrypted


def test_the_card_shows_only_while_the_system_part_is_full(tmp_path):
    from bau import setup_steps as S
    assert S._done("room", tmp_path, lambda w: w == "room" and True) is False
    assert S._done("room", tmp_path, lambda w: False) is None
    assert S._command("room", tmp_path).endswith("bau-make-room.sh")
