"""Download a registered local model file, verified against its pinned SHA-256.

A model record may carry `download: {url, file, size, sha256}`. The file is fetched to
`<dest>/<file>.part` (resumed if a part exists), hashed while it streams, and renamed into
place only when size and SHA-256 both match. A mismatch deletes the part: a wrong file is
never left where a model server could load it.
"""

from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

CHUNK = 1 << 20


class FetchError(RuntimeError):
    pass


def fetch(rec: dict[str, Any], dest: Path, opener: Callable[..., Any] | None = None,
          progress: Callable[[int, int], None] | None = None) -> Path:
    dl = rec.get("download") or {}
    url, name, want = dl.get("url"), dl.get("file"), str(dl.get("sha256", ""))
    if not (url and name and len(want) == 64):
        raise FetchError(f"{rec.get('model_id')} has no pinned download (url, file, sha256)")
    size = int(dl.get("size") or 0)
    opener = opener or urllib.request.urlopen
    dest.mkdir(parents=True, exist_ok=True)
    final, part = dest / name, dest / f"{name}.part"
    if final.exists() and _sha256(final) == want:
        return final

    h = hashlib.sha256()
    have = part.stat().st_size if part.exists() else 0
    if have:
        with part.open("rb") as f:
            while b := f.read(CHUNK):
                h.update(b)
    req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
    try:
        with opener(req, timeout=60) as r:
            if have and getattr(r, "status", 206) != 206:   # server ignored the range
                have, h = 0, hashlib.sha256()
            with part.open("ab" if have else "wb") as f:
                while b := r.read(CHUNK):
                    f.write(b)
                    h.update(b)
                    have += len(b)
                    if progress:
                        progress(have, size)
    except (urllib.error.URLError, OSError) as e:
        raise FetchError(f"download interrupted ({e}); run the same command again to resume"
                         ) from e

    if size and have != size:
        part.unlink(missing_ok=True)
        raise FetchError(f"size {have} != expected {size}: file deleted, download it again")
    if h.hexdigest() != want:
        part.unlink(missing_ok=True)
        raise FetchError("SHA-256 does not match the pinned value: file deleted (wrong or "
                         "tampered download)")
    part.replace(final)
    return final


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while b := f.read(CHUNK):
            h.update(b)
    return h.hexdigest()
