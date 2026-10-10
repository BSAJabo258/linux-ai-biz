"""USB #2 (make-payload.sh) builds even where git can't read the checkout."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not shutil.which("bash") or not shutil.which("sha256sum"),
                    reason="needs bash and sha256sum (Linux)")
def test_payload_builds_when_git_cannot_read_the_checkout(tmp_path):
    # Seen 2026-10-10 in a codespace copy mounted from Windows: git refused the folder
    # ("dubious ownership") and the script stopped silently under `set -e`.
    env = {**os.environ, "GIT_DIR": str(tmp_path / "no-such-repo"), "GIT_CEILING_DIRECTORIES": "/"}
    out = tmp_path / "out"
    r = subprocess.run(["bash", str(ROOT / "installer" / "make-payload.sh"), "--skip-tests",
                        "--out", str(out)], cwd=ROOT, env=env, capture_output=True, text=True,
                       timeout=600)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert "recorded as unknown" in r.stdout + r.stderr
    manifest = json.loads((out / "BAU-PAYLOAD" / "MANIFEST.json").read_text())
    assert manifest["git_commit"] == "unknown" and manifest["git_dirty"] is None
    assert (out / "BAU-PAYLOAD" / "SHA256SUMS").exists()
