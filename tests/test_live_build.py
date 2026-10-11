"""My Jarvis live image (build-live.sh): the finished ISO leaves the root-run build container."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Stands in for `docker run ... bash /work/inside.sh /work`. The real container runs as root,
# so out/ belongs to root and the host user cannot move the image out of it (build-live run
# 37674826251, 2026-10-07: "mv: cannot move ... Permission denied"). Only when the host user
# is passed in does inside.sh hand out/ back; the fake mimics that with chmod.
FAKE_DOCKER = """#!/usr/bin/env bash
set -euo pipefail
work="" uid=""
while (($#)); do
  case $1 in
    -v) work=${2%%:*}; shift 2 ;;
    -e) [[ $2 == HOST_UID=* ]] && uid=${2#HOST_UID=}; shift 2 ;;
    *) shift ;;
  esac
done
mkdir -p "$work/out"
echo iso > "$work/out/my-jarvis-$(cat "$IMAGE_VERSION_FILE")-amd64.iso"
echo '{}' > "$work/out/manifest.json"
[[ $uid == "$(id -u)" ]] || chmod 0555 "$work/out"
"""


@pytest.mark.skipif(not shutil.which("bash") or not shutil.which("sha256sum"),
                    reason="needs bash and sha256sum (Linux)")
@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                    reason="root ignores the read-only out/ this test relies on")
def test_live_image_is_moved_out_of_the_root_owned_build_folder(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER)
    docker.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
           "IMAGE_VERSION_FILE": str(ROOT / "image" / "VERSION")}
    out = tmp_path / "out"
    try:
        r = subprocess.run(["bash", str(ROOT / "image" / "build-live.sh"), "--skip-tests",
                            "--out", str(out)], cwd=ROOT, env=env, capture_output=True,
                           text=True, timeout=600)
    finally:
        if (out / "live-work" / "out").exists():
            (out / "live-work" / "out").chmod(0o755)   # let pytest clean up
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    version = (ROOT / "image" / "VERSION").read_text().strip()
    iso = out / f"my-jarvis-{version}-amd64.iso"
    assert iso.read_text() == "iso\n"
    assert json.loads((out / f"my-jarvis-{version}-amd64.manifest.json").read_text()) == {}
    assert (out / f"{iso.name}.sha256").read_text().split()[1] == iso.name
