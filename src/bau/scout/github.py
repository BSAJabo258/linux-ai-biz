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

Rate limits, checked on 2026-10-09 at docs.github.com/en/rest/using-the-rest-api
(rate-limits-for-the-rest-api, best-practices-for-using-the-rest-api):
- Other REST calls (README, fork parent) share the primary limit: 60 an hour without a
  token, 5,000 with one. Every answer carries ``x-ratelimit-remaining`` and
  ``x-ratelimit-reset`` (UTC epoch seconds).
- Over a limit GitHub answers 403 or 429. Do not retry before ``retry-after`` seconds; if
  ``x-ratelimit-remaining`` is 0, not before ``x-ratelimit-reset``; otherwise wait at least
  one minute, longer each time it repeats. "Continuing to make requests while you are rate
  limited may result in the banning of your integration."
- Make requests serially, never concurrently.
BAU does all of that: one request at a time, paced per limit, and the wait GitHub asks
for is stored in ``scout/github-rate.json`` so a second run (or Jarvis) honours it too.
While a wait is in force no request is sent at all.

The optional token (``GITHUB_TOKEN``) only raises the rate limit; it needs no scopes for
public repositories, and it is never passed to anything a candidate repository runs.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API = "https://api.github.com"
API_VERSION = "2026-03-10"
MIN_WAIT, MAX_WAIT = 60, 3600          # secondary limit with no instruction: 1 min, doubling


class SourceError(RuntimeError):
    """A search that could not be answered (rate limit, network, refused)."""


class RateLimited(SourceError):
    """GitHub asked BAU to wait. Nothing more is sent to it until ``until``."""

    def __init__(self, msg: str, until: float):
        super().__init__(msg)
        self.until = until

    @property
    def when(self) -> str:
        return dt.datetime.fromtimestamp(self.until, dt.UTC).strftime("%H:%M UTC")


class GitHub:
    name = "github"

    def __init__(self, token: str | None = None, opener: Any = None, sleep: Any = None,
                 pace: float | None = None, state: Path | None = None, clock: Any = None):
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN") or None
        self._open = opener or urllib.request.urlopen
        self.sleep = sleep or time.sleep
        self.clock = clock or time.time
        self.state_path = state
        # Seconds between requests, per limit: stay under 10 (or 30) searches a minute, and
        # spread the 60-an-hour core budget instead of spending it in a burst.
        self.pace = {"search": pace if pace is not None else (2.2 if self.token else 6.5),
                     "core": pace if pace is not None else (1.0 if self.token else 2.0)}
        self._mem: dict[str, Any] = {}

    # ---------------------------------------------------------------- shared state
    def _load(self) -> dict[str, Any]:
        if self.state_path is None:
            return self._mem
        try:
            return json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            return {}

    def _save(self, st: dict[str, Any]) -> None:
        if self.state_path is None:
            self._mem = st
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(st, sort_keys=True))
        tmp.replace(self.state_path)

    def waiting(self) -> RateLimited | None:
        """The wait GitHub asked for, if one is still in force."""
        st = self._load()
        until = max((b.get("blocked_until", 0) for b in st.values()
                     if isinstance(b, dict)), default=0)
        if until > self.clock():
            return RateLimited("GitHub asked BAU to wait", until)
        return None

    def _before(self, bucket: str) -> None:
        st = self._load()
        b = st.get(bucket) or {}
        now = self.clock()
        if b.get("blocked_until", 0) > now:
            raise RateLimited(f"GitHub asked BAU to wait ({bucket} limit); nothing was sent",
                              b["blocked_until"])
        wait = b.get("last", 0) + self.pace[bucket] - now
        if b.get("last") and wait > 0:
            self.sleep(wait)
        b["last"] = self.clock()
        st[bucket] = b
        self._save(st)

    def _after(self, bucket: str, headers: Any, limited: bool) -> float:
        """Record what GitHub said about its limits. Returns the time to wait until (0 when
        no wait is needed)."""
        st = self._load()
        b = st.get(bucket) or {}
        now = self.clock()
        get = (lambda k: headers.get(k)) if headers is not None else (lambda k: None)
        remaining, reset, retry = get("x-ratelimit-remaining"), get("x-ratelimit-reset"), \
            get("retry-after")
        until = 0.0
        try:
            if retry is not None:
                until = now + max(1, int(retry))
            elif remaining is not None and int(remaining) == 0 and reset is not None:
                until = float(reset)
        except ValueError:
            until = 0.0
        if limited and not until:
            strikes = b.get("strikes", 0)
            until = now + min(MAX_WAIT, MIN_WAIT * 2 ** strikes)
            b["strikes"] = strikes + 1
        elif not limited:
            b["strikes"] = 0
        if until:
            b["blocked_until"] = until
        if remaining is not None:
            b["remaining"] = remaining
        st[bucket] = b
        self._save(st)
        return until

    # ---------------------------------------------------------------- requests
    def _get(self, path: str, raw: bool = False, timeout: int = 30) -> Any:
        bucket = "search" if path.startswith("/search/") else "core"
        self._before(bucket)
        h = {"Accept": "application/vnd.github.raw+json" if raw else
             "application/vnd.github+json", "X-GitHub-Api-Version": API_VERSION,
             "User-Agent": "bau-repo-scout"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        try:
            with self._open(urllib.request.Request(API + path, headers=h),
                            timeout=timeout) as r:
                body = r.read()
                self._after(bucket, getattr(r, "headers", None), False)
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read() or b"{}").get("message") or e.reason
            except (ValueError, AttributeError, OSError):
                msg = e.reason
            hdr = e.headers
            limited = e.code == 429 or (e.code == 403 and hdr is not None and (
                hdr.get("retry-after") is not None or hdr.get("x-ratelimit-remaining") == "0"
                or "rate limit" in str(msg).lower()))
            if limited:
                until = self._after(bucket, hdr, True)
                err = RateLimited(f"GitHub rate limit (HTTP {e.code}): {str(msg)[:120]}", until)
                raise RateLimited(f"{err}. BAU will not ask again before {err.when}",
                                  until) from None
            raise SourceError(f"GitHub HTTP {e.code}: {str(msg)[:160]}") from None
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            raise SourceError(f"could not reach GitHub: {e}"[:200]) from None
        return body.decode("utf-8", "replace") if raw else json.loads(body)

    def search(self, query: str, per_page: int = 10) -> list[dict[str, Any]]:
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
