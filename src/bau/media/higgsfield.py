"""Higgsfield video generation (pay per clip), the studio's first generation provider.

Facts checked on 2026-10-10 at docs.higgsfield.ai (authentication, requests, polling,
rate-limits, billing-and-retention, quickstart, models/kling-3):
- Base URL ``https://api.higgsfield.ai``; header ``Authorization: Key ID:SECRET``, used
  server-side only (never in a browser).
- Submit: ``POST /<model path>`` with a JSON body and an ``Idempotency-Key`` header (send
  the same key again after a timeout). Answer: ``status, request_id, status_url,
  cancel_url``.
- Price first: ``POST /estimate/<model path>`` with the same body -> ``{credits, usd}``;
  the estimate for the account is the authoritative amount.
- Status: ``GET /requests/{id}/status``; ``queued`` and ``in_progress`` are not final,
  ``completed`` / ``failed`` / ``nsfw`` / ``canceled`` are. A finished video is at
  ``video.url``; output files are kept at least seven days, so BAU downloads them.
- Failed, moderated (``nsfw``) and timed-out requests are not charged; credits expire a
  year after purchase.
- Limit: how many requests may be queued or running at once, per account and model; when
  reached the API answers 400 ``Maximum number of concurrent requests (N) has been
  reached`` with no Retry-After; the docs ask for backoff with jitter and no tight loops.
- Kling 3.0 text-to-video bodies (checked on the Pro workflow page): ``prompt`` (up to
  2,500 characters), ``duration`` 3-15 s (default 5), ``aspect_ratio`` 16:9 / 9:16 / 1:1,
  ``sound`` on / off. Only those fields are sent.
Terms (help centre, 2026-10-10): the customer owns outputs and commercial use is not
restricted; Higgsfield may use content to train its models while it is kept there.
"""

from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API = "https://api.higgsfield.ai"
MODELS = {   # name -> endpoint (Kling 3.0 text-to-video workflows)
    "kling-3-turbo": "/kling-video/v3.0-turbo/text-to-video",
    "kling-3-std": "/kling-video/v3.0/std/text-to-video",
    "kling-3-pro": "/kling-video/v3.0/pro/text-to-video",
}
ASPECTS = ("16:9", "9:16", "1:1")
FINAL = {"completed", "failed", "nsfw", "canceled"}
MAX_VIDEO_BYTES = 1 << 30


class HiggsfieldError(RuntimeError):
    """A clip that could not be priced, started or finished. Never carries the key."""


class HiggsfieldBusy(HiggsfieldError):
    """The account's limit of clips in progress is reached; wait for one to finish."""


def request_body(model: str, prompt: str, duration: int, aspect_ratio: str,
                 sound: str) -> dict[str, Any]:
    if model not in MODELS:
        raise HiggsfieldError(f"unknown model {model!r}; choose one of {', '.join(MODELS)}")
    prompt = (prompt or "").strip()
    if not prompt:
        raise HiggsfieldError("a prompt is needed")
    if len(prompt) > 2500:
        raise HiggsfieldError("the prompt may be at most 2500 characters")
    if not isinstance(duration, int) or not 3 <= duration <= 15:
        raise HiggsfieldError("duration must be 3 to 15 seconds")
    if aspect_ratio not in ASPECTS:
        raise HiggsfieldError(f"aspect ratio must be one of {', '.join(ASPECTS)}")
    if sound not in ("on", "off"):
        raise HiggsfieldError("sound must be on or off")
    return {"prompt": prompt, "duration": duration, "aspect_ratio": aspect_ratio,
            "sound": sound}


class Higgsfield:
    name = "higgsfield"

    def __init__(self, key_id: str | None = None, secret: str | None = None,
                 opener: Any = None, sleep: Any = None, timeout: int = 60):
        self._key = (key_id if key_id is not None else os.environ.get("HIGGSFIELD_API_KEY_ID"),
                     secret if secret is not None else
                     os.environ.get("HIGGSFIELD_API_KEY_SECRET"))
        self._open = opener or urllib.request.urlopen
        self.sleep = sleep or time.sleep
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return all(self._key)

    def _call(self, method: str, url: str, body: dict[str, Any] | None = None,
              extra: dict[str, str] | None = None) -> dict[str, Any]:
        if not self.configured:
            raise HiggsfieldError("no Higgsfield key: set HIGGSFIELD_API_KEY_ID and "
                                  "HIGGSFIELD_API_KEY_SECRET (a Codespaces secret, or "
                                  "/etc/bau/models.env on the laptop)")
        h = {"Authorization": f"Key {self._key[0]}:{self._key[1]}",
             "Accept": "application/json", **(extra or {})}
        data = None
        if body is not None:
            data, h["Content-Type"] = json.dumps(body).encode(), "application/json"
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        try:
            with self._open(req, timeout=self.timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read() or b"{}").get("detail") or e.reason
            except (ValueError, AttributeError, OSError):
                detail = e.reason
            detail = str(detail)[:200]
            if e.code == 400 and "concurrent" in detail.lower():
                raise HiggsfieldBusy(f"Higgsfield is already making the most clips your "
                                     f"account allows at once ({detail}); wait for one to "
                                     "finish") from None
            if e.code == 401:
                raise HiggsfieldError("Higgsfield refused the key (HTTP 401): check "
                                      "HIGGSFIELD_API_KEY_ID / _SECRET") from None
            raise HiggsfieldError(f"Higgsfield HTTP {e.code}: {detail}") from None
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            raise HiggsfieldError(f"could not reach Higgsfield: {e}"[:200]) from None

    def estimate(self, model: str, body: dict[str, Any]) -> dict[str, Any]:
        r = self._call("POST", API + "/estimate" + MODELS[model], body)
        try:
            return {"credits": r["credits"], "usd": float(r["usd"])}
        except (KeyError, TypeError, ValueError):
            raise HiggsfieldError("Higgsfield returned no price for this clip") from None

    def submit(self, model: str, body: dict[str, Any], idempotency_key: str
               ) -> dict[str, Any]:
        r = self._call("POST", API + MODELS[model], body, {"Idempotency-Key": idempotency_key})
        if not r.get("request_id"):
            raise HiggsfieldError("Higgsfield accepted nothing (no request id)")
        return r

    def status(self, req: dict[str, Any]) -> dict[str, Any]:
        url = req.get("status_url") or f"{API}/requests/{req['request_id']}/status"
        if not url.startswith(API + "/"):
            raise HiggsfieldError("status address is not Higgsfield's")
        return self._call("GET", url)

    def wait(self, req: dict[str, Any], max_wait: float = 1800) -> dict[str, Any]:
        """Poll with backoff and jitter until the request is final. Returns the completed
        status; raises for failed, moderated or canceled requests (none are charged)."""
        delay, waited = 4.0, 0.0
        while True:
            st = self.status(req)
            s = st.get("status")
            if s in FINAL:
                break
            if waited >= max_wait:
                raise HiggsfieldError("the clip is taking too long; check it again later")
            pause = delay + random.uniform(0, delay / 2)
            self.sleep(pause)
            waited += pause
            delay = min(delay * 1.6, 30.0)
        if s != "completed":
            note = {"nsfw": "rejected by content moderation", "failed": "generation failed",
                    "canceled": "canceled"}[s]
            raise HiggsfieldError(f"{s}: {note}" + (f" ({str(st.get('error'))[:200]})"
                                                    if st.get("error") else ""))
        if not (st.get("video") or {}).get("url"):
            raise HiggsfieldError("completed, but Higgsfield returned no video address")
        return st

    def download(self, url: str, dest: Path) -> Path:
        if not str(url).startswith("https://"):
            raise HiggsfieldError("refusing a non-https download address")
        req = urllib.request.Request(url, headers={"User-Agent": "bau-studio"})
        tmp = dest.with_suffix(dest.suffix + ".part")
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._open(req, timeout=300) as r, tmp.open("wb") as fh:
                got = 0
                while chunk := r.read(1 << 20):
                    got += len(chunk)
                    if got > MAX_VIDEO_BYTES:
                        raise HiggsfieldError("video larger than 1 GB; not saved")
                    fh.write(chunk)
        except (urllib.error.URLError, OSError) as e:
            tmp.unlink(missing_ok=True)
            raise HiggsfieldError(f"download failed: {e}"[:200]) from None
        tmp.replace(dest)
        return dest
