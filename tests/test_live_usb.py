"""My Jarvis live USB: encrypted storage planning, verified model download, model record."""

import hashlib
import io
import urllib.error

import pytest
import yaml

from bau import live
from bau.models.fetch import FetchError, fetch
from bau.registry import validate
from bau.runtime import shipped_data

GiB = 1 << 30


def table(label, parts):
    return {"partitiontable": {"label": label, "partitions": [
        {"node": f"/dev/sdb{i}", "start": s, "size": n} for i, (s, n) in enumerate(parts, 1)]}}


def test_free_space_after_the_live_system_is_used_and_aligned():
    # A 3 GB live ISO on a 64 GB stick (hybrid MBR: ISO partition + EFI image inside it).
    t = table("dos", [(0, 6_000_000), (1000, 8192)])
    p = live.plan_free_space("/dev/sdb", t, 64 * GiB // 512, 512)
    assert p.start >= 6_000_000 and p.start % 2048 == 0
    assert p.start + p.size <= 64 * GiB // 512 and p.size % 2048 == 0
    assert not p.new_table and p.label == "dos" and p.gib > 55
    assert p.sfdisk_input() == f"start={p.start}, size={p.size}, type=83\n"


def test_gpt_keeps_room_for_its_backup_header():
    t = table("gpt", [(64, 6_000_000)])
    sectors = 32 * GiB // 512
    p = live.plan_free_space("/dev/sdb", t, sectors, 512)
    assert p.start + p.size <= sectors - 34
    assert live.LINUX_GPT in p.sfdisk_input()


def test_live_image_gpt_is_relocated_to_the_end_of_the_stick_first():
    # The real my-jarvis ISO written to a 16 GB stick (sfdisk --json, 2026-10-07).
    t = table("gpt", [(64, 312), (376, 6656), (7032, 1861052)])
    t["partitiontable"]["lastlba"] = 1868084
    sectors = 16 * GiB // 512
    assert live.needs_gpt_relocation(t, sectors)
    with pytest.raises(live.StorageError):            # before relocation: no room
        live.plan_free_space("/dev/sdb", t, sectors, 512)
    t["partitiontable"]["lastlba"] = sectors - 34       # after `sfdisk --relocate gpt-bak-std`
    assert not live.needs_gpt_relocation(t, sectors)
    p = live.plan_free_space("/dev/sdb", t, sectors, 512)
    assert p.start >= 1868084 and p.start + p.size <= sectors - 33 and p.gib > 14


def test_too_little_free_space_is_refused():
    t = table("dos", [(0, 6_000_000)])
    with pytest.raises(live.StorageError, match="need 4 GB"):
        live.plan_free_space("/dev/sdb", t, 7_000_000, 512)


def test_another_disk_is_used_only_when_completely_empty():
    sectors = 16 * GiB // 512
    p = live.plan_empty_disk("/dev/sdc", None, sectors, 512, mounted=False)
    assert p.new_table and p.label == "gpt"
    assert p.sfdisk_input().startswith("label: gpt\n")
    with pytest.raises(live.StorageError, match="never deletes"):
        live.plan_empty_disk("/dev/sdc", table("gpt", [(2048, 4096)]), sectors, 512, False)
    with pytest.raises(live.StorageError, match="mounted"):
        live.plan_empty_disk("/dev/sdc", None, sectors, 512, mounted=True)
    with pytest.raises(live.StorageError, match="smaller"):
        live.plan_empty_disk("/dev/sdc", None, 2 * GiB // 512, 512, False)


def test_only_private_folders_persist():
    dirs = [line.split()[0] for line in live.PERSISTENCE_CONF.splitlines()]
    assert dirs == ["/home", "/etc/bau", "/var/lib/bau", "/etc/NetworkManager/system-connections"]
    assert "/" not in dirs                       # the system itself stays read-only


@pytest.mark.parametrize("mounts,state", [
    ("/run/live/persistence/dm-0 /dev/mapper/sdb3\n/ overlay", "encrypted"),
    ("/run/live/persistence/sdb3 /dev/sdb3", "unencrypted"),
    ("/ overlay\n/run/live/medium /dev/sdb1", "none"),
])
def test_private_state_trusts_only_encrypted_persistence(monkeypatch, mounts, state):
    monkeypatch.setattr(live, "_out", lambda cmd: mounts)
    assert live.private_state() == state
    assert live.main(["status"]) == (0 if state == "encrypted" else 3)


# ------------------------------------------------------------------ verified download

class Resp(io.BytesIO):
    def __init__(self, data, status=200):
        super().__init__(data)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def rec(data, **kw):
    return {"model_id": "m", "download": {"url": "https://example.org/m.gguf", "file": "m.gguf",
            "size": len(data), "sha256": hashlib.sha256(data).hexdigest(), **kw}}


def test_fetch_verifies_and_places_the_file(tmp_path):
    data = b"GGUF" + b"x" * 5000
    seen = []
    out = fetch(rec(data), tmp_path, opener=lambda req, timeout: seen.append(req) or Resp(data))
    assert out.read_bytes() == data and not (tmp_path / "m.gguf.part").exists()
    # Already there and correct: nothing is downloaded again.
    assert fetch(rec(data), tmp_path, opener=lambda *a, **k: pytest.fail("refetched")) == out


def test_fetch_deletes_a_wrong_file(tmp_path):
    data = b"GGUF" + b"x" * 100
    dest = tmp_path / "models"
    with pytest.raises(FetchError, match="SHA-256"):
        fetch(rec(data), dest, opener=lambda req, timeout: Resp(b"EVIL" + b"x" * 100))
    assert not list(dest.iterdir())


def test_fetch_resumes_an_interrupted_download(tmp_path):
    data = b"GGUF" + b"y" * 3000
    (tmp_path / "m.gguf.part").write_bytes(data[:1000])
    reqs = []

    def opener(req, timeout):
        reqs.append(req)
        return Resp(data[1000:], status=206)
    assert fetch(rec(data), tmp_path, opener=opener).read_bytes() == data
    assert reqs[0].headers["Range"] == "bytes=1000-"


def test_fetch_failures_are_reported_never_hidden(tmp_path):
    with pytest.raises(FetchError, match="no pinned download"):
        fetch({"model_id": "m"}, tmp_path)

    def down(req, timeout):
        raise urllib.error.URLError("offline")
    with pytest.raises(FetchError, match="resume"):
        fetch(rec(b"abc"), tmp_path, opener=down)


def test_small_model_record_is_pinned_and_needs_bench_and_approval():
    r = yaml.safe_load((shipped_data() / "registry_defaults.yaml").read_text()
                       )["model"]["qwen2.5-1.5b-instruct"]
    assert r["status"] == "REGISTERED" and r["license"] == "Apache-2.0"
    assert r["deployment"] == "local" and r["endpoint"].startswith("http://127.0.0.1:")
    assert len(r["download"]["sha256"]) == 64 and r["download"]["url"].startswith("https://")
    assert validate("model", r) == []
    assert any("benchmark" in e for e in validate("model", {**r, "status": "APPROVED"}))
    bad = {**r, "download": {**r["download"], "sha256": "abc", "url": "http://x"}}
    assert {e.split()[0] for e in validate("model", bad)} == {"download.url", "download.sha256"}


def test_jarvis_uses_the_small_local_model_once_benchmarked_and_approved(tmp_path, monkeypatch):
    from bau.assistant import build_assistant
    from bau.models.providers import LocalHTTPProvider
    from bau.runtime import seed_registry
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    seed_registry(tmp_path)
    assert build_assistant(tmp_path).provider is None          # nothing approved: basic mode
    path = tmp_path / "registry" / "capabilities.yaml"
    data = yaml.safe_load(path.read_text())
    data["model"]["qwen2.5-1.5b-instruct"].update(status="APPROVED", benchmark={"reply_ok": True})
    path.write_text(yaml.safe_dump(data))
    a = build_assistant(tmp_path)
    assert a.model["id"] == "qwen2.5-1.5b-instruct" and isinstance(a.provider, LocalHTTPProvider)


def test_live_image_keeps_the_safety_model():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "image" / "live-build"
    cfg = (root / "auto" / "config").read_text()
    assert "persistence-encryption=lukslabel" in cfg     # never plain or foreign storage
    assert '"syslinux,grub-efi"' in cfg                  # partition_offset: stick stays usable
    menu = (root / "grub.cfg").read_text()
    assert menu.count("@APPEND_LIVE@") >= 4 and "nopersistence" in menu
    init = (root / "config/includes.chroot/usr/local/sbin/bau-live-init").read_text()
    assert init.index("jarvis-storage status") < init.index("audit.key")   # keys only if private
    hook = (root / "config/hooks/live/0500-bau.hook.chroot").read_text()
    assert "ConditionPathExists=/run/bau-live/private" in hook
    assert "urandom" not in hook and "ssh-keygen" not in hook     # no keys baked into the image
    unit = (root / "config/includes.chroot/etc/systemd/system/bau-live-init.service").read_text()
    assert "Before=systemd-user-sessions.service" in unit     # groups exist before any login
    llm = (root / "config/includes.chroot/etc/systemd/system/bau-llm.service").read_text()
    assert "--host 127.0.0.1" in llm and "User=bau" in llm


def test_live_image_has_a_display_server_for_the_desktop():
    # --apt-recommends false: xfce4 and lightdm only *recommend* Xorg, so without these
    # lines the image has no X server and LightDM fails at every boot.
    from pathlib import Path
    lst = Path(__file__).resolve().parents[1] / "image/live-build/config/package-lists"
    pkgs = {line.split("#")[0].strip() for f in lst.glob("*.list.chroot")
            for line in f.read_text().splitlines()}
    assert {"xserver-xorg", "xserver-xorg-core", "lightdm", "lightdm-gtk-greeter"} <= pkgs


def test_live_image_installs_the_claude_sdk_offline():
    from pathlib import Path
    image = Path(__file__).resolve().parents[1] / "image"
    build = (image / "build-live.sh").read_text()
    assert "--with-claude" in build and "wheels/*.whl" in build
    hook = (image / "live-build/config/hooks/live/0500-bau.hook.chroot").read_text()
    assert "--no-index --find-links /opt/bau/wheels anthropic" in hook
    assert hook.index("import anthropic") < hook.index("rm -rf /opt/bau/wheels")
    assert "ANTHROPIC_API_KEY" not in hook                         # the key is never in the image


# Fakes for jarvis-setup: storage unlocked, owner in the bau group, sudo without root
# (chown skipped), and a `bau` that keeps model status in a file and logs every call.
FAKES = {
    "jarvis-storage": "exit 0",
    "id": "echo owner bau bau-approvers",
    "sudo": '[[ $1 == chown ]] && exit 0\necho "sudo $*" >> "$LOG"\nexec "$@"',
    "bau": """echo "bau $*" >> "$LOG"
case "$1 $2" in
  "models list") printf '[{"model_id": "claude-opus-5-5", "status": "%s"}]' "$(cat "$STATE")" ;;
  "models bench") exit "${BENCH_EXIT:-0}" ;;
  "set-status model") echo "$4" > "$STATE" ;;
esac""",
}


def run_setup(tmp_path, answers, bench_exit=0):
    import os
    import subprocess
    from pathlib import Path
    script = (Path(__file__).resolve().parents[1] / "image/live-build/config/includes.chroot"
              / "usr/local/bin/jarvis-setup")
    bin_dir, etc = tmp_path / "bin", tmp_path / "etc"
    bin_dir.mkdir()
    etc.mkdir()
    for name, body in FAKES.items():
        (bin_dir / name).write_text("#!/bin/bash\n" + body + "\n")
        (bin_dir / name).chmod(0o755)
    (tmp_path / "state").write_text("NOT_EVALUATED")
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "BAU_ETC": str(etc),
           "LOG": str(tmp_path / "log"), "STATE": str(tmp_path / "state"),
           "BENCH_EXIT": str(bench_exit)}
    r = subprocess.run(["bash", str(script)], input=answers, env=env, capture_output=True,
                       text=True, timeout=60)
    log = (tmp_path / "log").read_text() if (tmp_path / "log").exists() else ""
    return r, etc / "models.env", log, (tmp_path / "state").read_text().strip()


@pytest.mark.skipif(not __import__("shutil").which("bash"), reason="needs bash")
def test_live_setup_keeps_the_claude_key_private_and_waits_for_the_owner(tmp_path):
    key = "sk-ant-test-0123456789"
    # Use Claude? y / key / Approve? y / Download the local model? n / Talk now? n
    r, env_file, log, state = run_setup(tmp_path, f"y\n{key}\ny\nn\nn\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert env_file.read_text() == f"ANTHROPIC_API_KEY={key}\n"
    assert env_file.stat().st_mode & 0o777 == 0o640
    assert key not in r.stdout + r.stderr and key not in log    # not shown, not in any argv
    assert "bau models bench claude-opus-5-5" in log            # measured before approval
    assert state == "APPROVED"                                  # by the owner's own y
    assert "bau models fetch" not in log                        # local model is optional now

    (tmp_path / "declined").mkdir()
    r, env_file, log, _ = run_setup(tmp_path / "declined", "n\nn\n")   # no Claude, no model
    assert r.returncode == 0 and not env_file.exists()
    assert "bench" not in log and "set-status" not in log


@pytest.mark.skipif(not __import__("shutil").which("bash"), reason="needs bash")
def test_live_setup_never_approves_claude_without_the_owner_or_a_working_key(tmp_path):
    (tmp_path / "a").mkdir()
    r, _, log, state = run_setup(tmp_path / "a", "y\nsk-ant-test\nn\nn\n")    # owner says no
    assert "set-status" not in log and state == "NOT_EVALUATED"
    assert "Not approved" in r.stdout
    (tmp_path / "b").mkdir()
    r, _, log, state = run_setup(tmp_path / "b", "y\nsk-ant-test\n", bench_exit=1)
    assert "set-status" not in log and state == "NOT_EVALUATED"
    assert "cannot be approved" in r.stdout
