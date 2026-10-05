"""Benchmark a model where it actually runs (spec §6: never fake local availability).

A local model can be approved only after it has answered on this machine. The benchmark
times a short reply, measures generation speed, and checks the model can call a tool -
Jarvis and the agents depend on that. The result is stored on the registry record.
"""

from __future__ import annotations

import datetime as dt
import time
from typing import Any

from .providers import Provider, ToolSpec, build

PROBE_TOOL = ToolSpec("get_time", "Return the current time.",
                      {"type": "object", "properties": {}, "required": []})


def benchmark(rec: dict[str, Any], provider: Provider | None = None) -> dict[str, Any]:
    p = provider or build(rec)
    t0 = time.monotonic()
    r = p.complete("You answer in one short sentence.",
                   [{"role": "user", "content": "Say hello and name one colour."}],
                   None, max_tokens=1024)
    took = time.monotonic() - t0
    t1 = time.monotonic()
    rt = p.complete("Use a tool whenever one can answer the question.",
                    [{"role": "user", "content": "What time is it right now? Use get_time."}],
                    [PROBE_TOOL], max_tokens=1024)
    took_tool = time.monotonic() - t1
    return {
        "at": dt.datetime.now(dt.UTC).isoformat(),
        "endpoint": getattr(p, "base_url", None),
        "served_model": r.model,
        "reply_ok": bool(r.text.strip()) and not r.refused,
        "latency_ms": int(took * 1000),
        "tokens_per_sec": round(r.tokens_out / took, 1) if r.tokens_out and took else None,
        "tool_calls": any(c.name == PROBE_TOOL.name for c in rt.tool_calls),
        "tool_latency_ms": int(took_tool * 1000),
    }
