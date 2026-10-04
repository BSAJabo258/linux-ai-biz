"""Model provider adapters behind one interface (spec §112 adapter principle).

* AnthropicProvider    - Claude through the official ``anthropic`` SDK (optional
                         dependency: ``pip install 'bau[claude]'``).
* LocalHTTPProvider    - a local inference server (llama.cpp ``llama-server`` or
                         Ollama) on 127.0.0.1; also how K3 is reached when it runs
                         locally or on an offload box you control.
* ScriptedProvider     - deterministic replies for tests and offline dry runs.

Conversation history is append-only: the provider returns the raw assistant
content and the agent appends it unchanged (needed for thinking-block replay).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ModelResponse:
    text: str
    tool_calls: list[ToolCall]
    stop_reason: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    refused: bool = False
    refusal_category: str | None = None
    raw_assistant: Any = None           # content to append back verbatim
    served_by_fallback: bool = False


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


class Provider:
    provider_id = "base"

    def complete(self, system: str, messages: list[dict[str, Any]],
                 tools: list[ToolSpec] | None = None, max_tokens: int = 16000
                 ) -> ModelResponse:
        raise NotImplementedError

    def tool_result_message(self, results: list[tuple[ToolCall, str, bool]]) -> dict[str, Any]:
        """Build the user turn that returns tool results (all of them, in one message)."""
        raise NotImplementedError

    def health(self) -> dict[str, Any]:
        return {"ok": True}


# ------------------------------------------------------------------ Claude

class AnthropicProvider(Provider):
    """Claude via the official SDK. Refusals are checked before content is read, and
    server-side fallbacks are on by default so a classifier decline is retried on
    Anthropic's recommended model instead of failing the job."""

    provider_id = "anthropic"

    def __init__(self, model: str = "claude-opus-5-5", effort: str = "high",
                 client: Any = None, fallbacks: bool = True):
        self.model = model
        self.effort = effort
        self.fallbacks = fallbacks
        if client is None:
            import anthropic  # optional dependency
            client = anthropic.Anthropic()
        self.client = client

    @staticmethod
    def _tool(t: ToolSpec) -> dict[str, Any]:
        schema = dict(t.input_schema)
        schema.setdefault("type", "object")
        schema.setdefault("additionalProperties", False)
        schema.setdefault("required", list(schema.get("properties", {})))
        return {"name": t.name, "description": t.description, "input_schema": schema,
                "strict": True}

    def complete(self, system, messages, tools=None, max_tokens=16000):
        kwargs: dict[str, Any] = dict(
            model=self.model, max_tokens=max_tokens, system=system, messages=messages,
            output_config={"effort": self.effort})
        if tools:
            kwargs["tools"] = [self._tool(t) for t in tools]
        if self.fallbacks:
            resp = self.client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"],
                extra_body={"fallbacks": "default"}, **kwargs)
        else:
            resp = self.client.messages.create(**kwargs)
        usage = getattr(resp, "usage", None)
        tin = getattr(usage, "input_tokens", 0) or 0
        tout = getattr(usage, "output_tokens", 0) or 0
        if resp.stop_reason == "refusal":
            details = getattr(resp, "stop_details", None)
            return ModelResponse(text="", tool_calls=[], stop_reason="refusal",
                                 model=resp.model, tokens_in=tin, tokens_out=tout,
                                 refused=True,
                                 refusal_category=getattr(details, "category", None),
                                 raw_assistant=None)
        text, calls = [], []
        for block in resp.content:
            if block.type == "text":
                text.append(block.text)
            elif block.type == "tool_use":
                calls.append(ToolCall(block.id, block.name, dict(block.input)))
        iterations = getattr(usage, "iterations", None) or []
        fell_back = any(getattr(i, "type", "") == "fallback_message" for i in iterations)
        return ModelResponse(text="\n".join(text), tool_calls=calls,
                             stop_reason=resp.stop_reason, model=resp.model, tokens_in=tin,
                             tokens_out=tout, raw_assistant=resp.content,
                             served_by_fallback=fell_back)

    def tool_result_message(self, results):
        return {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": c.id, "content": out, "is_error": err}
            for c, out, err in results]}

    def health(self):
        has_cred = any(os.environ.get(k) for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
                                                    "ANTHROPIC_PROFILE"))
        return {"ok": True, "credentials_in_env": has_cred,
                "note": "SDK also resolves `ant auth login` profiles"}


# ------------------------------------------------------------------ local server

class LocalHTTPProvider(Provider):
    """llama.cpp ``llama-server`` / Ollama chat endpoint on a host you control."""

    provider_id = "local"

    def __init__(self, base_url: str = "http://127.0.0.1:8080", model: str = "local",
                 timeout: int = 600, opener: Any = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._open = opener or urllib.request.urlopen

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(self.base_url + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with self._open(req, timeout=self.timeout) as r:
            return json.loads(r.read())

    def complete(self, system, messages, tools=None, max_tokens=16000):
        msgs = [{"role": "system", "content": system}] + messages
        body: dict[str, Any] = {"model": self.model, "messages": msgs,
                                "max_tokens": max_tokens}
        if tools:
            body["tools"] = [{"type": "function", "function": {
                "name": t.name, "description": t.description,
                "parameters": t.input_schema}} for t in tools]
        data = self._post("/v1/chat/completions", body)
        choice = data["choices"][0]
        msg = choice["message"]
        calls = []
        for tc in msg.get("tool_calls") or []:
            args = tc["function"].get("arguments") or "{}"
            calls.append(ToolCall(tc.get("id", tc["function"]["name"]), tc["function"]["name"],
                                  json.loads(args) if isinstance(args, str) else args))
        usage = data.get("usage") or {}
        return ModelResponse(text=msg.get("content") or "", tool_calls=calls,
                             stop_reason="tool_use" if calls else "end_turn",
                             model=data.get("model", self.model),
                             tokens_in=usage.get("prompt_tokens", 0),
                             tokens_out=usage.get("completion_tokens", 0),
                             raw_assistant=msg)

    def tool_result_message(self, results):
        # OpenAI-style servers take one "tool" message per call; returned as a list
        # the agent extends the history with.
        return {"role": "_multi", "content": [
            {"role": "tool", "tool_call_id": c.id, "content": out} for c, out, _ in results]}

    def health(self):
        try:
            req = urllib.request.Request(self.base_url + "/v1/models")
            with self._open(req, timeout=5) as r:
                models = json.loads(r.read()).get("data", [])
            return {"ok": True, "models": [m.get("id") for m in models]}
        except (urllib.error.URLError, OSError, ValueError) as e:
            return {"ok": False, "error": str(e)[:200]}


# ------------------------------------------------------------------ scripted

@dataclass
class ScriptedProvider(Provider):
    """Replays a fixed list of responses. Each item: str (final text) or
    {"tool": name, "input": {...}} (one tool call)."""

    script: list[Any] = field(default_factory=list)
    provider_id: str = "scripted"
    calls: list[dict[str, Any]] = field(default_factory=list)

    def complete(self, system, messages, tools=None, max_tokens=16000):
        self.calls.append({"system": system, "messages": list(messages),
                           "tools": [t.name for t in tools or []]})
        if not self.script:
            return ModelResponse("done", [], "end_turn", "scripted",
                                 raw_assistant=[{"type": "text", "text": "done"}])
        item = self.script.pop(0)
        if isinstance(item, str):
            return ModelResponse(item, [], "end_turn", "scripted", 10, 5,
                                 raw_assistant=[{"type": "text", "text": item}])
        if item.get("refuse"):
            return ModelResponse("", [], "refusal", "scripted", refused=True,
                                 refusal_category=item.get("category"))
        call = ToolCall(f"call_{len(self.calls)}", item["tool"], item.get("input", {}))
        return ModelResponse("", [call], "tool_use", "scripted", 10, 5,
                             raw_assistant=[{"type": "tool_use", "id": call.id,
                                             "name": call.name, "input": call.input}])

    def tool_result_message(self, results):
        return {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": c.id, "content": out, "is_error": err}
            for c, out, err in results]}


def build(record: dict[str, Any]) -> Provider:
    """Instantiate a provider from a model-registry record."""
    kind = record.get("adapter", "local_http")
    if kind == "anthropic":
        return AnthropicProvider(model=record.get("api_model", "claude-opus-5-5"),
                                 effort=record.get("effort", "high"))
    if kind == "local_http":
        return LocalHTTPProvider(base_url=record.get("endpoint", "http://127.0.0.1:8080"),
                                 model=record.get("api_model", record["model_id"]))
    if kind == "scripted":
        return ScriptedProvider(list(record.get("script", [])))
    raise ValueError(f"unknown adapter {kind}")
