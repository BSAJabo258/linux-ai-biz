"""One place for every platform's sign-in tokens (Fanvue, TikTok, and the ones to come).

Found on 2026-11-18 (the owner: "the terminal connects, Jarvis doesn't reuse it"): each
platform kept its own token file locked to the account that signed in (folder 0700, file 0600).
The owner signs in as his own login, but the autopilot that posts and syncs earnings runs as
the ``bau`` account, so it could never read the token. And a refresh token works once: Jarvis
and the autopilot refreshing at the same moment left one of them told to connect again.

Here, for every platform:
- one file, ``BAU_HOME/secrets/<platform>.json``, readable by the owner's login and the ``bau``
  account through the shared ``bau`` group (folder 2770, file 0660), never by anyone else -
  the same rule as ``/etc/bau/platforms.env`` (root:bau 0640);
- one lock around a refresh, so the second process re-reads the token the first one saved
  instead of spending the used refresh token;
- a token that is there but cannot be read is said plainly, with the fix, never shown as
  "not connected".
Tokens are never printed or logged.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .home import atomic_write_json, bau_home

DIR_MODE = 0o2770     # the owner's login and the bau account (group), new files keep the group
FILE_MODE = 0o660


class CredentialError(RuntimeError):
    pass


def fix_command(path: Path) -> str:
    folder = path.parent
    return (f"sudo chgrp -R bau {folder} && sudo chmod 2770 {folder} && "
            f"sudo chmod 660 {folder}/*.json")


class Store:
    """The one token file of one platform."""

    def __init__(self, platform: str, home: Path | None = None):
        self.platform = platform
        self.path = (home or bau_home()) / "secrets" / f"{platform}.json"

    def _share(self, p: Path, mode: int) -> None:
        """Widen an older owner-only file to the shared group; only its owner can."""
        try:
            st = p.stat()
            if st.st_uid == os.getuid() and (st.st_mode & 0o7777) != mode:
                os.chmod(p, mode)
        except OSError:
            pass

    def load(self) -> dict[str, Any] | None:
        try:
            if not self.path.exists():
                return None
            self._share(self.path.parent, DIR_MODE)
            self._share(self.path, FILE_MODE)
            return json.loads(self.path.read_text())
        except PermissionError:
            raise CredentialError(
                f"the {self.platform} sign-in is on this computer but this account cannot "
                f"read it ({self.path}). Fix it once: {fix_command(self.path)}") from None

    def save(self, rec: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._share(self.path.parent, DIR_MODE)
        atomic_write_json(self.path, rec)
        os.chmod(self.path, FILE_MODE)

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()

    def state(self) -> str:
        """missing / unreadable / present: what this account sees, nothing secret."""
        try:
            return "present" if self.load() is not None else "missing"
        except CredentialError:
            return "unreadable"

    @contextlib.contextmanager
    def refresh_lock(self) -> Iterator[None]:
        """Held while a token is refreshed: the next process waits, then re-reads."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix(".lock")
        fd = os.open(lock, os.O_RDWR | os.O_CREAT, FILE_MODE)
        try:
            self._share(lock, FILE_MODE)
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
