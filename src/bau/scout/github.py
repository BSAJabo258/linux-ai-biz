"""GitHub as a Repo Scout source: read-only search and metadata, never a write.

Facts checked on 2026-10-09 against docs.github.com/en/rest/search/search:
- ``GET /search/repositories?q=...&per_page=...`` (per_page max 100; at most 1,000 results
  per search). Items carry full_name, html_url, description, fork, license (spdx_id),
  archived, pushed_at, stargazers_count, topics, language, size (KB).
- Search rate limit: 10 requests/minute without a token, 30 with one. BAU paces itself
  below that and reports a 403/429 as a failed search, never as "nothing found".
- Headers: ``Accept: application/vnd.github+json``, ``X-GitHub-Api-Version: 2026-03-10``,
  optional ``Authorization: Bearer <token>``.
``GET /repos/{owner}/{repo}`` gives a fork's ``parent``/``source``; ``GET
/repos/{owner}/{repo}/readme`` with ``Accept: application/vnd.github.raw+json`` gives the
README text, which is untrusted data.

The optional token (``GITHUB_TOKEN``) only raises the rate limit; it needs no scopes for
public repositories, and it is never passed to anything a candidate repository runs.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API = "https://api.github.com"
API_VERSION = "2026-03-10"


class SourceError(RuntimeError):
    """A search that could not be answered (rate limit, network, refused)."""


class GitHub:
    name = "github"

    def __init__(self, token: str | None = None, opener: Any = None, sleep: Any = None,
                 pace: float | None = None):
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN") or None
        self._open = opener or urllib.request.urlopen
        self.sleep = sleep or time.sleep
        # Stay under 10 (or 30) searches a minute.
        self.pace = pace if pace is not None else (2.2 if self.token else 6.5)
        self._last = 0.0

    def _get(self, path: str, raw: bool = False, timeout: int = 30) -> Any:
        h = {"Accept": "application/vnd.github.raw+json" if raw else
             "application/vnd.github+json", "X-GitHub-Api-Version": API_VERSION,
             "User-Agent": "bau-repo-scout"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        try:
            with self._open(urllib.request.Request(API + path, headers=h),
                            timeout=timeout) as r:
                body = r.read()
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read() or b"{}").get("message") or e.reason
            except (ValueError, AttributeError, OSError):
                msg = e.reason
            if e.code in (403, 429):
                raise SourceError(f"GitHub refused or rate-limited the request (HTTP {e.code}):"
                                  f" {str(msg)[:160]}") from None
            raise SourceError(f"GitHub HTTP {e.code}: {str(msg)[:160]}") from None
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            raise SourceError(f"could not reach GitHub: {e}"[:200]) from None
        return body.decode("utf-8", "replace") if raw else json.loads(body)

    def search(self, query: str, per_page: int = 10) -> list[dict[str, Any]]:
        wait = self._last + self.pace - time.monotonic()
        if self._last and wait > 0:
            self.sleep(wait)
        self._last = time.monotonic()
        q = urllib.parse.urlencode({"q": f"{query} in:name,description,topics,readme",
                                    "per_page": max(1, min(per_page, 100))})
        data = self._get(f"/search/repositories?{q}")
        if not isinstance(data, dict):
            raise SourceError("GitHub returned something that is not a search result")
        if data.get("message") and "items" not in data:
            raise SourceError(f"GitHub: {str(data['message'])[:160]}")
        return [normalise(i) for i in data.get("items") or [] if isinstance(i, dict)]

    def repo(self, full_name: str) -> dict[str, Any]:
        return self._get(f"/repos/{urllib.parse.quote(full_name, safe='/')}")

    def upstream(self, full_name: str) -> str | None:
        r = self.repo(full_name)
        src = r.get("source") or r.get("parent") or {}
        return src.get("full_name")

    def readme(self, full_name: str) -> str:
        text = self._get(f"/repos/{urllib.parse.quote(full_name, safe='/')}/readme", raw=True)
        return text[:20000]


def normalise(i: dict[str, Any]) -> dict[str, Any]:
    lic = i.get("license") or {}
    spdx = lic.get("spdx_id") if isinstance(lic, dict) else None
    return {"full_name": str(i.get("full_name", "")), "url": i.get("html_url"),
            "description": (i.get("description") or "")[:400],
            "topics": [str(t) for t in (i.get("topics") or [])][:20],
            "language": i.get("language"), "fork": bool(i.get("fork")),
            "archived": bool(i.get("archived")), "pushed_at": i.get("pushed_at"),
            "stars": i.get("stargazers_count"), "size_kb": i.get("size"),
            "homepage": i.get("homepage") or None,
            # GitHub says NOASSERTION when it can't tell: that is unknown, not a licence.
            "license_spdx": None if spdx in (None, "", "NOASSERTION") else spdx}
