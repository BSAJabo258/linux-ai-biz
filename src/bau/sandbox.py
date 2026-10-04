"""Sandbox runner for untrusted code (spec §100, §37).

Untrusted repositories, tools and models run only in a rootless Podman
container with: no network (unless explicitly allowed), read-only root,
all capabilities dropped, no-new-privileges, memory/CPU/PID limits, a
throwaway workspace, and the repository mounted read-only. Only intake
states from QUARANTINED onwards may run, and only with a signed approval.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .security.sentinel import STATES

RUNNABLE_FROM = STATES.index("QUARANTINED")


@dataclass
class SandboxProfile:
    image: str = "docker.io/library/python:3.13-slim"
    network: str = "none"            # none | slirp4netns (only with explicit approval)
    memory: str = "2g"
    cpus: str = "2"
    pids: int = 256
    timeout_s: int = 900
    env: dict[str, str] = field(default_factory=dict)   # never secrets


def command(repo: Path, cmd: list[str], profile: SandboxProfile, workspace: Path) -> list[str]:
    podman = shutil.which("podman") or "podman"
    if any(k.upper().endswith(("KEY", "TOKEN", "SECRET", "PASSWORD")) for k in profile.env):
        raise PermissionError("secrets are never passed into a sandbox")
    base = [podman, "run", "--rm", "--userns=keep-id", f"--network={profile.network}",
            "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
            f"--memory={profile.memory}", f"--cpus={profile.cpus}",
            f"--pids-limit={profile.pids}", "--tmpfs=/tmp:rw,size=512m,noexec",
            f"--volume={repo.resolve()}:/src:ro,Z",
            f"--volume={workspace.resolve()}:/work:rw,Z", "--workdir=/work"]
    for k, v in sorted(profile.env.items()):
        base.append(f"--env={k}={v}")
    return base + [profile.image, *cmd]


def run(repo: Path, cmd: list[str], intake_state: str, approved: bool,
        profile: SandboxProfile | None = None, workspace: Path | None = None,
        dry_run: bool = False) -> dict[str, Any]:
    if intake_state not in STATES or STATES.index(intake_state) < RUNNABLE_FROM:
        raise PermissionError(f"intake state {intake_state}: not yet eligible to execute")
    if not approved:
        raise PermissionError("running untrusted code needs a signed approval")
    profile = profile or SandboxProfile()
    if profile.network != "none" and not approved:
        raise PermissionError("network inside the sandbox needs approval")
    workspace = workspace or Path(repo).parent / (Path(repo).name + ".sandbox-work")
    workspace.mkdir(parents=True, exist_ok=True)
    full = command(repo, cmd, profile, workspace)
    if dry_run:
        return {"dry_run": True, "command": full}
    r = subprocess.run(full, capture_output=True, text=True, timeout=profile.timeout_s,
                       check=False)
    return {"returncode": r.returncode, "stdout": r.stdout[-20000:],
            "stderr": r.stderr[-20000:], "command": full}
