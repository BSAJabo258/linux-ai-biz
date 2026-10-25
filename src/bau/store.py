"""Small persistence helpers shared by the ledgers and registries.

JSONL files are append-only logs (ledgers, events). YAML files are human-edited
registries. Both live under BAU_HOME so backups and the golden baseline see them.
"""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml


def fresh_line(fh: Any) -> bytes:
    """A newline if the file does not end with one: a record cut off by a power cut stays
    on its own line instead of swallowing the next one (audit 2026-10-25)."""
    fh.seek(0, os.SEEK_END)
    if fh.tell() == 0:
        return b""
    fh.seek(-1, os.SEEK_END)
    return b"" if fh.read(1) == b"\n" else b"\n"


def read_lines(path: Path) -> Iterator[dict[str, Any] | None]:
    """Each record of a JSONL file; None for a line that was cut off mid-write."""
    if not path.exists():
        return
    with path.open() as fh:
        for line in fh:
            if line.strip():
                try:
                    yield json.loads(line)
                except ValueError:
                    yield None


class JsonlStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, rec: dict[str, Any]) -> dict[str, Any]:
        with self.path.open("ab+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                fh.write(fresh_line(fh) + (json.dumps(rec, sort_keys=True, default=str)
                                           + "\n").encode())
                fh.flush()
                os.fsync(fh.fileno())
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
        return rec

    def __iter__(self) -> Iterator[dict[str, Any]]:
        yield from (r for r in read_lines(self.path) if r is not None)

    def all(self) -> list[dict[str, Any]]:
        return list(self)

    def rewrite(self, recs: list[dict[str, Any]]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text("".join(json.dumps(r, sort_keys=True, default=str) + "\n" for r in recs))
        tmp.replace(self.path)


class YamlStore:
    def __init__(self, path: Path, default: Any = None):
        self.path = path
        self.default = {} if default is None else default

    def load(self) -> Any:
        if not self.path.exists():
            return json.loads(json.dumps(self.default))
        data = yaml.safe_load(self.path.read_text())
        return self.default if data is None else data

    def save(self, data: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(yaml.safe_dump(data, sort_keys=True, allow_unicode=True))
        tmp.replace(self.path)
