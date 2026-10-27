"""The CUDA engine for the desktop (docs/GPU.md): `sudo bau-llm-cuda build` builds llama.cpp
with NVIDIA's CUDA beside the stick's Vulkan engine, from the same pinned commit, after the
owner's y; `use cuda` / `use vulkan` switch which one the model server runs. Proved
2026-10-27 in debian:trixie: nvidia-cuda-toolkit 12.4.131 builds b11747 with GGML_CUDA."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONF = ROOT / "image" / "live-build" / "config"
SCRIPT = CONF / "includes.chroot" / "usr" / "local" / "sbin" / "bau-llm-cuda"
COMMIT = "f711c8f3038020d71f69b8ced09162b014fd7335"


def machine(tmp_path, driver=True, live=False, nonfree=True, head=COMMIT, root=True):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    log = tmp_path / "calls.log"

    def cmd(name, body):
        (bin_ / name).write_text(f"#!/bin/sh\necho \"{name} $*\" >> {log}\n{body}\n")
        (bin_ / name).chmod(0o755)

    cmd("id", "echo 0" if root else "echo 1000")
    cmd("apt-get", "exit 0")
    cmd("apt-cache", "echo '  Candidate: 12.4.131~12.4.1-2'" if nonfree
        else "echo '  Candidate: (none)'")
    cmd("nvidia-smi", "echo 8.6")
    cmd("nproc", "echo 4")
    cmd("systemctl", "exit 0")
    # git clone makes the source tree; rev-parse answers with the commit it checked out
    cmd("git", f'case "$1" in clone) mkdir -p "$8" && touch "$8/LICENSE";; '
        f'-C) echo {head};; esac')
    # cmake --build makes the parts a CUDA build makes
    cmd("cmake", 'if [ "$1" = --build ]; then mkdir -p "$2/bin" && touch "$2/bin/llama-server" '
        '"$2/bin/libggml-cuda.so" "$2/bin/libggml-base.so" && chmod +x "$2/bin/llama-server"; fi')
    (tmp_path / "opt").mkdir()
    (tmp_path / "opt" / "VERSION").write_text(f"b11747 {COMMIT}\n")
    nv = tmp_path / "nvidia-version"
    if driver:
        nv.write_text("NVRM version: 550.163.01\n")
    live_dir = tmp_path / "live"
    if live:
        live_dir.mkdir()
    env = {"PATH": f"{bin_}:/usr/bin:/bin", "BAU_LIVE_MEDIUM": str(live_dir),
           "BAU_NVIDIA_PROC": str(nv), "BAU_LLAMA_VERSION": str(tmp_path / "opt" / "VERSION"),
           "BAU_CUDA_DIR": str(tmp_path / "opt" / "llama.cpp-cuda"),
           "BAU_ENGINE_ENV": str(tmp_path / "etc" / "llm-engine.env"),
           "BAU_BUILD_DIR": str(tmp_path / "work")}
    return env, log


def run(env, *args, answers=""):
    return subprocess.run(["bash", str(SCRIPT), *args], env=env, input=answers,
                          capture_output=True, text=True, timeout=60)


def calls(log):
    return log.read_text().splitlines() if log.exists() else []


def test_nothing_is_installed_without_the_owners_yes(tmp_path):
    env, log = machine(tmp_path)
    r = run(env, "build", answers="n\n")
    assert "nothing was changed" in r.stdout.lower()
    assert not any(c.startswith("apt-get install") for c in calls(log))


def test_build_uses_the_stick_commit_and_the_cards_own_level(tmp_path):
    env, log = machine(tmp_path)
    r = run(env, "build", answers="y\n")
    assert r.returncode == 0, r.stdout + r.stderr
    inst = [c for c in calls(log) if c.startswith("apt-get install")][0]
    assert "nvidia-cuda-toolkit" in inst
    assert any("--branch b11747" in c for c in calls(log))
    conf = [c for c in calls(log) if c.startswith("cmake -S")][0]
    assert "-DGGML_CUDA=ON" in conf and "-DCMAKE_CUDA_ARCHITECTURES=86" in conf
    dest = tmp_path / "opt" / "llama.cpp-cuda"
    assert (dest / "libggml-cuda.so").exists()
    assert (dest / "VERSION").read_text().split()[:3] == ["b11747", COMMIT, "cuda"]
    assert not (tmp_path / "etc" / "llm-engine.env").exists()     # built, not switched


def test_a_different_commit_is_refused(tmp_path):
    env, _ = machine(tmp_path, head="0" * 40)
    r = run(env, "build", answers="y\n")
    assert r.returncode != 0 and "refusing" in r.stdout
    assert not (tmp_path / "opt" / "llama.cpp-cuda").exists()


def test_refuses_on_the_live_stick_without_the_driver_or_without_sudo(tmp_path):
    for kw, word in (({"live": True}, "live stick"), ({"driver": False}, "bau-gpu-setup"),
                     ({"root": False}, "sudo")):
        d = tmp_path / word.replace(" ", "")
        d.mkdir()
        env, log = machine(d, **kw)
        r = run(env, "build", answers="y\n")
        assert r.returncode != 0 and word in r.stdout
        assert not any(c.startswith("apt-get install") for c in calls(log))


def test_use_switches_the_engine_and_back(tmp_path):
    env, log = machine(tmp_path)
    assert run(env, "use", "cuda").returncode != 0                   # not built yet
    run(env, "build", answers="y\n")
    assert run(env, "use", "cuda").returncode == 0
    engine = (tmp_path / "etc" / "llm-engine.env").read_text()
    assert f"BAU_LLAMA_SERVER={tmp_path}/opt/llama.cpp-cuda/llama-server" in engine
    assert "restart bau-llm.service" in " ".join(calls(log))
    assert "uses: cuda" in run(env, "status").stdout
    assert run(env, "use", "vulkan").returncode == 0
    assert not (tmp_path / "etc" / "llm-engine.env").exists()
    assert "uses: vulkan" in run(env, "status").stdout


def test_the_service_reads_the_engine_file_and_the_hook_makes_it_runnable():
    svc = (CONF / "includes.chroot" / "etc" / "systemd" / "system" / "bau-llm.service")
    text = svc.read_text()
    assert "EnvironmentFile=-/etc/bau/llm-engine.env" in text
    assert text.index("EnvironmentFile=/etc/bau/llm.env") < text.index("llm-engine.env")
    hook = (CONF / "hooks" / "live" / "0500-bau.hook.chroot").read_text()
    assert "/usr/local/sbin/bau-llm-cuda" in hook
