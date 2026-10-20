"""Bringing the owner's API keys to the laptop (`bau keys`, docs/KEYS.md).

The export scripts on the owner's other computer (installer/bau-keys-export.ps1 / .sh)
write BAU-KEYS.enc: a text file starting with HEADER, one NAME=value per line, locked
with openssl's `enc -aes-256-cbc -pbkdf2 -md sha256` format and a passphrase the owner
chooses. Here it is opened and each key goes to the file BAU reads it from:
platform app keys to /etc/bau/platforms.env, every other key to /etc/bau/models.env
(root:bau 0640). Values are never printed, logged or audited - names only.
"""

from __future__ import annotations

import grp
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

HEADER = "# BAU-KEYS v1"
ITERATIONS = 600_000
ETC = Path("/etc/bau")
# Only credential-shaped names, so a key file can never set PATH, LD_PRELOAD or BAU's own
# settings. The export scripts use the same pattern.
NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*(API_KEY[A-Z0-9_]*|_KEY|_TOKEN|_SECRET|_CLIENT_ID"
                     r"|_KEY_ID)$")
NEVER = ("BAU_", "LD_", "PYTHON")
PLATFORMS = ("TIKTOK_", "YOUTUBE_", "INSTAGRAM_", "FACEBOOK_", "META_", "PINTEREST_",
             "TWITTER_", "X_", "LINKEDIN_")


class KeyFileError(ValueError):
    pass


def decrypt(path: Path, passphrase: str) -> str:
    if not shutil.which("openssl"):
        raise KeyFileError("openssl is needed to open the key file (sudo apt install openssl)")
    r = subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter",
                        str(ITERATIONS), "-md", "sha256", "-in", str(path), "-pass",
                        "env:BAU_KEYS_PASSPHRASE"],
                       env={**os.environ, "BAU_KEYS_PASSPHRASE": passphrase},
                       capture_output=True)
    if r.returncode != 0:
        raise KeyFileError("could not open the key file: wrong passphrase or a damaged file")
    try:
        return r.stdout.decode("utf-8")
    except UnicodeDecodeError as e:
        raise KeyFileError("not a BAU keys file (or a wrong passphrase)") from e


def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v


def parse(text: str) -> dict[str, str]:
    body = [(n, ln.strip()) for n, ln in enumerate(text.splitlines(), 1) if ln.strip()]
    if not body or body[0][1] != HEADER:
        raise KeyFileError("not a BAU keys file (or a wrong passphrase)")
    out: dict[str, str] = {}
    for n, ln in body[1:]:
        if ln.startswith("#"):
            continue
        ln = ln.removeprefix("export ").strip()
        name, sep, value = ln.partition("=")
        name, value = name.strip(), _unquote(value)
        # By line number only: a bad line can be part of a secret (a key over several lines).
        if not sep or not NAME_RE.match(name) or name.startswith(NEVER):
            raise KeyFileError(f"line {n} is not NAME=value with an API key name")
        if any(c in value for c in "\"'\\") or any(ord(c) < 32 for c in value):
            raise KeyFileError(f"line {n} ({name}): the value has characters a key never has")
        if value:
            out[name] = value
    return out


def route(keys: dict[str, str]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for name, value in keys.items():
        f = "platforms.env" if name.startswith(PLATFORMS) else "models.env"
        out.setdefault(f, {})[name] = value
    return out


def _line(name: str, value: str) -> str:
    return f'{name}="{value}"' if re.search(r"[\s#]", value) else f"{name}={value}"


def merge(path: Path, new: dict[str, str]) -> None:
    """Replace the names it brings, keep every other line, write 0640 (root:bau as root)."""
    old = path.read_text().splitlines() if path.exists() else []
    left = dict(new)
    lines = []
    for ln in old:
        name = ln.strip().removeprefix("export ").partition("=")[0].strip()
        if name in left:
            lines.append(_line(name, left.pop(name)))
        else:
            lines.append(ln)
    lines += [_line(n, v) for n, v in left.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".new")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(tmp, 0o640)
    if os.geteuid() == 0:
        try:
            os.chown(tmp, 0, grp.getgrnam("bau").gr_gid)
        except KeyError:
            pass
    os.replace(tmp, path)


def import_file(path: Path, passphrase: str, etc: Path = ETC, audit: Any = None,
                actor: str = "human:owner") -> dict[str, Any]:
    keys = parse(decrypt(Path(path), passphrase))
    if not keys:
        raise KeyFileError("the key file has no keys in it")
    written = {}
    for fname, group in sorted(route(keys).items()):
        merge(Path(etc) / fname, group)
        written[fname] = sorted(group)
    if audit is not None:
        audit.append("keys.imported", actor, {"source": Path(path).name, "names": written})
    return {"written": written,
            "next": "delete the key file from the USB stick; then log out and in, so "
                    "Jarvis and BAU's services see the keys"}


def names(etc: Path = ETC) -> dict[str, list[str]]:
    out = {}
    for fname in ("models.env", "platforms.env"):
        p = Path(etc) / fname
        try:
            lines = p.read_text().splitlines()
        except OSError:
            continue
        out[fname] = sorted(n for n in (ln.strip().removeprefix("export ").partition("=")[0]
                                        .strip() for ln in lines if "=" in ln)
                            if n and not n.startswith("#"))
    return out
