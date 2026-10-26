"""For model choices: this computer's memory, graphics card, processor, disk and model engine.

`bau hw profile` only reads (the pre-wipe audit is `hardware.py`). Nothing is assumed: the
card's memory comes from NVIDIA's own `nvidia-smi --query-gpu` (the field names and the
"CUDA Version:" header are in Debian 13's nvidia-smi 550.163.01, checked in its binary
2026-10-26; its --help-query-gpu needs a card); without NVIDIA's driver it is "unknown",
never a guess.
System memory and card memory are kept apart: a model on the card is fast, one spilling
into system memory is much slower. A missing tool or a refused file is written down, never
read as "this part is absent".

`fits()` estimates whether a model file can run before anything is downloaded: the file
plus a margin for the engine and an 8K-word context. It is an estimate and says so;
`bau models lab` measures the real use.
"""

from __future__ import annotations

import datetime as dt
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .home import bau_home
from .store import YamlStore

GiB = 1 << 30
MiB = 1 << 20
ENGINE = Path("/opt/llama.cpp")
# Kept free on top of what Linux already counts as in use, for the browser and Jarvis's page
# to grow, when a model is in system memory (the 4B ran on the 8 GB laptop, 2026-10-21).
KEEP_FREE = 3 * GiB // 2
# The model engine's own buffers plus an 8K context on top of the file (estimate).
ENGINE_MARGIN = 1 * GiB
GPU_QUERY = "name,memory.total,memory.used,memory.free,driver_version,compute_cap"

Run = Callable[..., Any]


def _read(path: Path) -> str | None:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return None


def _cmd(run: Run, args: list[str]) -> tuple[str | None, str | None]:
    """(output, None) or (None, why). Read-only commands only."""
    try:
        p = run(args, capture_output=True, text=True, timeout=20)
    except FileNotFoundError:
        return None, f"{args[0]} is not installed"
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"{args[0]}: {type(e).__name__}"
    if p.returncode != 0:
        return None, f"{args[0]} answered {p.returncode}: {(p.stderr or '').strip()[:200]}"
    return p.stdout, None


def _os(root: Path) -> dict[str, Any]:
    rel = {}
    for line in (_read(root / "etc/os-release") or "").splitlines():
        k, _, v = line.partition("=")
        rel[k] = v.strip().strip('"')
    return {"name": rel.get("PRETTY_NAME"), "kernel": platform.release(),
            "arch": platform.machine(), "python": sys.version.split()[0]}


def _cpu(root: Path, run: Run) -> dict[str, Any]:
    model = next((ln.split(":", 1)[1].strip() for ln in
                  (_read(root / "proc/cpuinfo") or "").splitlines()
                  if ln.startswith("model name")), None)
    out, _ = _cmd(run, ["lscpu", "-p=core,socket"])
    cores = len({ln for ln in (out or "").splitlines() if ln and not ln.startswith("#")})
    return {"model": model, "threads": os.cpu_count(), "cores": cores or None}


def _memory(root: Path) -> dict[str, Any]:
    info = {}
    for line in (_read(root / "proc/meminfo") or "").splitlines():
        k, _, v = line.partition(":")
        parts = v.split()
        if parts and parts[0].isdigit():
            info[k] = int(parts[0]) * 1024
    return {"total": info.get("MemTotal"), "available": info.get("MemAvailable"),
            "swap": info.get("SwapTotal")}


def _nvidia_present(root: Path) -> bool:
    for dev in (root / "sys/bus/pci/devices").glob("*"):
        if ((_read(dev / "vendor") or "").strip() == "0x10de"
                and (_read(dev / "class") or "").strip().startswith("0x03")):
            return True
    return False


def _gpus(root: Path, run: Run) -> dict[str, Any]:
    present = _nvidia_present(root)
    driver = (root / "proc/driver/nvidia/version").exists()
    out, why = _cmd(run, ["nvidia-smi", f"--query-gpu={GPU_QUERY}",
                          "--format=csv,noheader,nounits"])
    cards = []
    for line in (out or "").splitlines():
        f = [x.strip() for x in line.split(",")]
        if len(f) < 6:
            continue

        def mib(x: str) -> int | None:
            return int(float(x)) * MiB if x.replace(".", "", 1).isdigit() else None
        cards.append({"name": f[0], "memory_total": mib(f[1]), "memory_used": mib(f[2]),
                      "memory_free": mib(f[3]), "driver": f[4], "compute_cap": f[5]})
    head, _ = _cmd(run, ["nvidia-smi"]) if cards else (None, None)
    cuda = next((ln.split("CUDA Version:")[1].strip(" |\n").split()[0]
                 for ln in (head or "").splitlines() if "CUDA Version:" in ln), None)
    note = None
    if present and not cards:
        note = ("an NVIDIA card is in this computer, but its memory is unknown until "
                "NVIDIA's driver runs (`sudo bau-gpu-setup`)" + (f"; {why}" if why else ""))
    return {"nvidia_card": present or bool(cards), "nvidia_driver_loaded": driver,
            "cards": cards, "driver_cuda": cuda,
            "cuda_toolkit": bool(shutil.which("nvcc")), "note": note}


def _engine(engine: Path, run: Run) -> dict[str, Any]:
    server = engine / "llama-server"
    version = None
    if server.exists():
        try:
            p = run([str(server), "--version"], capture_output=True, text=True, timeout=20,
                    env={**os.environ, "LD_LIBRARY_PATH": str(engine)})
            version = ((p.stdout or "") + (p.stderr or "")).strip().splitlines()[-1:] or None
        except (OSError, subprocess.TimeoutExpired):
            version = None
    return {"llama_server": server.exists(), "version": version[0] if version else None,
            "vulkan": (engine / "libggml-vulkan.so").exists(),
            "cuda": (engine / "libggml-cuda.so").exists(),
            "others": sorted(t for t in ("ollama", "docker", "podman") if shutil.which(t))}


def _disk(path: Path) -> dict[str, Any]:
    while not path.exists() and path != path.parent:
        path = path.parent
    try:
        u = shutil.disk_usage(path)
    except OSError as e:
        return {"path": str(path), "error": type(e).__name__}
    return {"path": str(path), "total": u.total, "free": u.free}


def _models(models: Path) -> list[dict[str, Any]]:
    try:
        return sorted(({"file": p.name, "size": p.stat().st_size}
                       for p in models.glob("*.gguf")), key=lambda m: m["file"])
    except OSError:
        return []


def profile(home: Path | None = None, root: Path = Path("/"), run: Run = subprocess.run,
            engine: Path = ENGINE) -> dict[str, Any]:
    home = home or bau_home()
    from .keys import names
    return {"at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "system": _os(root), "cpu": _cpu(root, run), "memory": _memory(root),
            "gpu": _gpus(root, run), "engine": _engine(engine, run),
            "disk": _disk(home / "models"), "models": _models(home / "models"),
            "key_names": names()}


def save(prof: dict[str, Any], home: Path | None = None) -> Path:
    home = home or bau_home()
    (home / "config").mkdir(parents=True, exist_ok=True)
    store = YamlStore(home / "config" / "hardware.yaml")
    store.save(prof)
    return store.path


def saved(home: Path | None = None) -> dict[str, Any]:
    return YamlStore((home or bau_home()) / "config" / "hardware.yaml").load() or {}


def fits(size: int, prof: dict[str, Any]) -> dict[str, Any]:
    """Where a model file of ``size`` bytes could run, estimated from a profile."""
    need = size + ENGINE_MARGIN
    mem = (prof.get("memory") or {}).get("available") or 0
    gpu = prof.get("gpu") or {}
    cards = gpu.get("cards") or []
    free_disk = (prof.get("disk") or {}).get("free")
    out: dict[str, Any] = {"file": size, "needs_about": need, "estimate": True,
                           "disk_ok": free_disk is None or free_disk > size * 1.05}
    vram = max((c.get("memory_free") or 0 for c in cards), default=0)
    if cards and need <= vram * 0.95:
        out.update(where="card", why="fits in the card's free memory: fastest")
    elif cards and need <= vram + max(mem - KEEP_FREE, 0):
        out.update(where="card+memory",
                   why="part on the card, the rest in system memory: works, but slower")
    elif gpu.get("nvidia_card") and not cards:
        out.update(where="unknown", why=gpu.get("note") or "the card's memory is unknown")
    elif need <= mem - KEEP_FREE:
        out.update(where="memory", why="in system memory on the processor: slow")
    else:
        out.update(where="no", why="too big for this computer's free memory")
    return out


def summary(prof: dict[str, Any]) -> dict[str, Any]:
    """The short version for the owner: sizes in GB."""
    def gb(n: Any) -> float | None:
        return round(n / GiB, 1) if isinstance(n, int) else None
    mem, gpu = prof.get("memory") or {}, prof.get("gpu") or {}
    return {
        "system": (prof.get("system") or {}).get("name"),
        "processor": (prof.get("cpu") or {}).get("model"),
        "memory_gb": {"total": gb(mem.get("total")), "free": gb(mem.get("available"))},
        "graphics_card": [{"name": c["name"], "card_memory_gb": gb(c.get("memory_total")),
                           "card_memory_free_gb": gb(c.get("memory_free")),
                           "driver": c.get("driver")} for c in gpu.get("cards") or []]
        or gpu.get("note") or "no NVIDIA card found",
        "model_engine": prof.get("engine"),
        "disk_free_gb": gb((prof.get("disk") or {}).get("free")),
        "models_here": [m["file"] for m in prof.get("models") or []],
    }
