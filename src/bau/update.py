"""Automatic updates for BAU on the owner's desktop (docs/UPDATES.md).

The owner's choice (2026-11-01, "fully automatic"): once a night the desktop installs the
newest BAU that passed every check, by itself, and puts the previous one back by itself if
Jarvis's side fails. This replaces "a person promotes each update" for BAU's own code only;
models, keys and approvals are untouched. Off until the owner turns it on (`sudo bau update
auto`), never a default.

Where updates come from: CI (.github/workflows/update-wheel.yml) builds the wheel only after
the ci workflow passed on a push to main, and puts it with bau-update.json (commit, wheel,
sha256) on the release "bau-update" of this public repository. A push to main happens only
when the owner merges.

Runs as root from bau-update.timer (pip writes /opt/bau/venv). Kept builds live in
/opt/bau/update, root-owned, so the bau account can never plant a wheel that root installs.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

RELEASE = "https://github.com/BSAJabo258/linux-ai-biz/releases/download/bau-update/"
CONF = Path("/etc/bau/update.conf")
STATE = Path("/opt/bau/update")
VENV = Path("/opt/bau/venv")
FIRST = Path("/opt/bau-payload/wheels")          # the stick's own wheel, the first way back
UI = "http://127.0.0.1:8765/"
SERVICES = ("bau-ui.service", "bau-jarvis.service")
RUN_AS = "bau"
WHEEL = re.compile(r"^bau-[0-9][0-9A-Za-z.+]*-py3-none-any\.whl$")
HEX40, HEX64 = re.compile(r"^[0-9a-f]{40}$"), re.compile(r"^[0-9a-f]{64}$")
MAX_WHEEL = 50 * 1024 * 1024
FRESH_HOURS = 36
LIVE = Path("/run/live/medium")


def mode(conf: Path = CONF) -> str | None:
    """"auto", "off", or None when the owner has not chosen."""
    try:
        for line in conf.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "mode" and value.strip() in ("auto", "off"):
                return value.strip()
    except OSError:
        pass
    return None


def set_mode(value: str, conf: Path = CONF) -> None:
    if value not in ("auto", "off"):
        raise ValueError("mode is auto or off")
    conf.parent.mkdir(parents=True, exist_ok=True)
    conf.write_text(f"# set by the owner with: sudo bau update {value}\nmode={value}\n")
    conf.chmod(0o644)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _record(state_dir: Path, rec: dict[str, Any]) -> dict[str, Any]:
    rec = {"at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), **rec}
    state_dir.mkdir(parents=True, exist_ok=True)
    state_dir.chmod(0o755)                                  # root writes, everyone reads
    (state_dir / "last.json").write_text(json.dumps(rec, indent=1))
    (state_dir / "last.json").chmod(0o644)                  # Jarvis (bau account) reads it
    return rec


def last(state_dir: Path | None = None) -> dict[str, Any] | None:
    """The last update, if it happened in the last day and a half (for the briefing)."""
    rec = _read_json((state_dir or STATE) / "last.json")
    if not rec or rec.get("result") not in ("installed", "rolled back", "broken"):
        return None
    try:
        age = dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(rec["at"])
    except (KeyError, ValueError):
        return None
    return rec if age < dt.timedelta(hours=FRESH_HOURS) else None


def status(state_dir: Path = STATE, conf: Path = CONF) -> dict[str, Any]:
    cur = _read_json(state_dir / "state.json") or {}
    return {"mode": mode(conf) or "not chosen (sudo bau update auto | off)",
            "installed_commit": cur.get("commit", "the stick's own build"),
            "last": _read_json(state_dir / "last.json")}


def problems(m: Any) -> list[str]:
    if not isinstance(m, dict):
        return ["the manifest is not a JSON object"]
    out = []
    if not HEX40.match(str(m.get("commit", ""))):
        out.append("commit is not a full git commit id")
    if not WHEEL.match(str(m.get("wheel", ""))):
        out.append("wheel is not a BAU wheel name")
    if not HEX64.match(str(m.get("sha256", ""))):
        out.append("sha256 is not 64 hex digits")
    return out


def _fetch(opener: Any, url: str, limit: int) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "bau-update"})
    with opener(req, timeout=120) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"{url} is larger than {limit} bytes")
    return data


def _can_update(wheel: Path) -> bool:
    """A build without this updater must never be the way back: after going back to it,
    nothing would update again (the owner's desktop, 2026-11-01: the stick's own build)."""
    try:
        with zipfile.ZipFile(wheel) as z:
            return "bau/update.py" in z.namelist()
    except (OSError, zipfile.BadZipFile):
        return False


def _previous(state_dir: Path, first_dir: Path) -> Path | None:
    for d in (state_dir / "current", first_dir):
        found = sorted(p for p in d.glob("bau-*.whl")
                       if WHEEL.match(p.name) and _can_update(p)) if d.is_dir() else []
        if found:
            return found[-1]
    return None


def keep(wheel: Path, commit: str, state_dir: Path = STATE) -> None:
    """Record a build installed outside the nightly run (installer/bau-update-first.sh) as the
    one to go back to."""
    if not HEX40.match(commit) or not WHEEL.match(wheel.name) or not _can_update(wheel):
        raise ValueError("not a BAU build with the updater, or not a full commit id")
    cur = state_dir / "current"
    shutil.rmtree(cur, ignore_errors=True)
    cur.mkdir(parents=True)
    state_dir.chmod(0o755)
    shutil.copy2(wheel, cur / wheel.name)
    (state_dir / "state.json").write_text(json.dumps({"commit": commit, "wheel": wheel.name}))


def _pip(runner: Callable[[list[str]], int], wheel: Path) -> bool:
    # Files readable by the bau account whatever umask root has (sudo can carry a strict one).
    old = os.umask(0o022)
    try:
        return runner([str(VENV / "bin" / "pip"), "install", "--quiet", "--no-index",
                       "--no-deps", "--force-reinstall", str(wheel)]) == 0
    finally:
        os.umask(old)


def _ui_answers(url: str = UI, tries: int = 30, sleep: Callable[[float], None] = time.sleep,
                opener: Any = urllib.request.urlopen) -> bool:
    for _ in range(tries):
        try:
            with opener(url, timeout=5) as r:
                if r.status == 200:
                    return True
        except OSError:
            pass
        sleep(1)
    return False


def _healthy(runner: Callable[[list[str]], int], ui_check: Callable[[], bool],
             sleep: Callable[[float], None], ui_was_up: bool = True) -> str | None:
    """None when the new BAU works; else what failed."""
    # As the bau account, which runs Mission Control: root can read files it cannot.
    if runner(["runuser", "-u", RUN_AS, "--", str(VENV / "bin" / "python"), "-I", "-c",
               "import bau.cli, bau.cli_ext, bau.assistant, bau.ui.jarvis_server"]) != 0:
        return "the new version does not start for the bau account (import failed)"
    for unit in SERVICES:
        if runner(["systemctl", "is-enabled", "--quiet", unit]) != 0:
            continue
        runner(["systemctl", "reset-failed", unit])          # clear systemd's start limit
        if runner(["systemctl", "restart", unit]) != 0:
            return f"{unit} did not restart"
    sleep(3)
    if ui_was_up and not ui_check():      # only if it answered before: not BAU's to blame
        return "Mission Control did not answer on 127.0.0.1:8765"
    return None


def run(opener: Any = None, runner: Callable[[list[str]], int] | None = None,
        state_dir: Path = STATE, conf: Path = CONF, first_dir: Path = FIRST,
        audit: Callable[[tuple[str, dict[str, Any]]], None] | None = None,
        ui_check: Callable[[], bool] | None = None,
        sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """One nightly pass. Returns {"result": off | up to date | refused | installed |
    rolled back | broken, ...}."""
    if mode(conf) != "auto":
        return {"result": "off"}
    if LIVE.exists():
        return {"result": "off", "why": "the live stick is rebuilt, not updated"}
    opener = opener or urllib.request.urlopen
    runner = runner or (lambda cmd: subprocess.run(cmd, check=False).returncode)
    ui_check = ui_check or (lambda: _ui_answers(sleep=sleep))

    def done(event: str, rec: dict[str, Any]) -> dict[str, Any]:
        rec = _record(state_dir, rec)
        if audit:
            audit((event, rec))
        return rec

    try:
        m = json.loads(_fetch(opener, RELEASE + "bau-update.json", 64 * 1024))
    except (OSError, ValueError) as e:
        return {"result": "no answer", "why": f"{type(e).__name__}: {e}"[:200]}
    if bad := problems(m):
        return done("update.refused", {"result": "refused", "why": "; ".join(bad)})
    current = _read_json(state_dir / "state.json") or {}
    if current.get("commit") == m["commit"]:
        return {"result": "up to date", "commit": m["commit"]}
    previous = _previous(state_dir, first_dir)
    if previous is None:
        return done("update.refused", {"result": "refused", "commit": m["commit"],
                                       "why": "no earlier build to go back to that can "
                                              "update itself; run installer/"
                                              "bau-update-first.sh once"})
    try:
        body = _fetch(opener, RELEASE + m["wheel"], MAX_WHEEL)
    except (OSError, ValueError) as e:
        return {"result": "no answer", "why": f"{type(e).__name__}: {e}"[:200]}
    if hashlib.sha256(body).hexdigest() != m["sha256"]:
        return done("update.refused", {"result": "refused", "commit": m["commit"],
                                       "why": "the download does not match its SHA-256"})
    incoming = state_dir / "incoming"
    shutil.rmtree(incoming, ignore_errors=True)
    incoming.mkdir(parents=True)
    new = incoming / m["wheel"]
    new.write_bytes(body)
    rec = {"commit": m["commit"], "wheel": m["wheel"], "previous": previous.name}
    ui_was_up = runner(["systemctl", "is-active", "--quiet", "bau-ui.service"]) == 0
    # Stopped while pip swaps the files: on the owner's desktop (2026-11-01) Mission Control
    # restarted mid-install, found no bau.cli five times and systemd gave up on it.
    for unit in SERVICES:
        runner(["systemctl", "stop", unit])

    why = None if _pip(runner, new) else "pip could not install it"
    why = why or _healthy(runner, ui_check, sleep, ui_was_up)
    if why is None:
        cur = state_dir / "current"
        shutil.rmtree(cur, ignore_errors=True)
        incoming.rename(cur)
        (state_dir / "state.json").write_text(json.dumps({"commit": m["commit"],
                                                          "wheel": m["wheel"]}))
        return done("update.installed", {"result": "installed", **rec})
    back = _pip(runner, previous) and _healthy(runner, ui_check, sleep, ui_was_up) is None
    shutil.rmtree(incoming, ignore_errors=True)
    if back:
        return done("update.rolled_back", {"result": "rolled back", "why": why, **rec})
    return done("update.broken", {"result": "broken", **rec,
                                  "why": f"{why}; going back also failed. Run: sudo bau "
                                         "update now, or reinstall: sudo bash "
                                         "/opt/bau-payload/install.sh"})
