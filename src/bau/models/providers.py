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
import re
import time
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

    chat_path = "/v1/chat/completions"

    def __init__(self, base_url: str = "http://127.0.0.1:8080", model: str = "local",
                 timeout: int = 600, opener: Any = None,
                 template_kwargs: dict[str, Any] | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.template_kwargs = template_kwargs or {}
        self.extra_body: dict[str, Any] = {}
        self.timeout = timeout
        self._open = opener or urllib.request.urlopen

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(self.base_url + path, data=json.dumps(body).encode(),
                                     headers=self._headers())
        with self._open(req, timeout=self.timeout) as r:
            return json.loads(r.read())

    def complete(self, system, messages, tools=None, max_tokens=16000):
        msgs = [{"role": "system", "content": system}] + messages
        body: dict[str, Any] = {"model": self.model, "messages": msgs,
                                "max_tokens": max_tokens}
        if self.template_kwargs:     # e.g. {"enable_thinking": false} for GLM / Qwen3
            body["chat_template_kwargs"] = self.template_kwargs
        body.update(self.extra_body)
        if tools:
            body["tools"] = [{"type": "function", "function": {
                "name": t.name, "description": t.description,
                "parameters": t.input_schema}} for t in tools]
        data = self._post(self.chat_path, body)
        choice = data["choices"][0]
        msg = choice["message"]
        calls = []
        for tc in msg.get("tool_calls") or []:
            args = tc["function"].get("arguments") or "{}"
            calls.append(ToolCall(tc.get("id", tc["function"]["name"]), tc["function"]["name"],
                                  json.loads(args) if isinstance(args, str) else args))
        usage = data.get("usage") or {}
        # Reasoning models (GLM, Qwen3...) may inline their thinking; never speak it.
        text = re.sub(r"<think>.*?</think>", "", msg.get("content") or "", flags=re.S).strip()
        return ModelResponse(text=text, tool_calls=calls,
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


class OpenAICompatProvider(LocalHTTPProvider):
    """A hosted OpenAI-compatible chat API (e.g. Z.ai). The key is read from the environment
    variable the registry record names (never stored in the registry or the repository)."""

    provider_id = "openai_compat"

    def __init__(self, base_url: str, model: str, api_key: str, chat_path: str,
                 extra_body: dict[str, Any] | None = None, timeout: int = 120,
                 opener: Any = None):
        super().__init__(base_url, model, timeout, opener)
        self.api_key = api_key
        self.chat_path = chat_path
        self.extra_body = dict(extra_body or {})

    # Free hosted tiers answer 429 "overloaded" when busy (Z.ai error 1305, seen on the
    # first real bench 2026-10-07: four busy replies, then success). Wait and try again
    # rather than fail the owner's conversation; give up with the service's own words.
    # Z.ai also answers a one-off 500 "Operation failed" mid-conversation (seen in the
    # owner's Codespace 2026-10-07; the same questions answered fine moments later).
    BUSY = (429, 500, 502, 503, 504)
    waits = (5, 10, 20, 40)
    sleep = staticmethod(time.sleep)

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}

    def _post(self, path, body):
        for attempt in range(len(self.waits) + 1):
            try:
                return super()._post(path, body)
            except urllib.error.HTTPError as e:
                said = _service_message(e)
                if e.code not in self.BUSY:
                    raise ProviderError(f"{self.base_url} refused the request "
                                        f"(HTTP {e.code}): {said}") from None
                if attempt == len(self.waits):
                    raise ProviderError(f"{self.base_url} is busy (HTTP {e.code}): {said}. "
                                        "Free services get crowded; try again in a few "
                                        "minutes.") from None
                self.sleep(_retry_after(e, self.waits[attempt]))
        raise AssertionError("unreachable")

    def health(self):
        return {"ok": None, "note": "hosted model: checked on first call (bau models bench)"}


class ProviderError(RuntimeError):
    """A hosted model refused or stayed busy; the message is safe to show the owner."""


def _service_message(e: urllib.error.HTTPError) -> str:
    try:
        data = json.loads(e.read() or b"{}")
        err = data.get("error") if isinstance(data, dict) else None
        msg = err.get("message") if isinstance(err, dict) else err
        return str(msg or e.reason)[:200]
    except (ValueError, OSError, AttributeError):
        return str(e.reason)[:200]


def _retry_after(e: urllib.error.HTTPError, default: int) -> int:
    try:
        return max(1, min(60, int(e.headers.get("Retry-After", default))))
    except (TypeError, ValueError, AttributeError):
        return default


class FallbackProvider(Provider):
    """The owner's approved hosted models, in their order. When one is busy, refuses or
    doesn't answer, the next answers the same turn; the one that failed rests for ten
    minutes before it is tried first again. Only OpenAI-compatible providers are chained,
    so tool calls and tool results keep one format whichever model answers."""

    provider_id = "fallback"
    REST = 600
    clock = staticmethod(time.monotonic)

    def __init__(self, providers: list[Provider]):
        self.providers = list(providers)
        self._resting: dict[int, float] = {}

    def complete(self, system, messages, tools=None, max_tokens=16000):
        now = self.clock()
        order = sorted(range(len(self.providers)), key=lambda i: self._resting.get(i, 0) > now)
        failed = []
        for i in order:
            try:
                r = self.providers[i].complete(system, messages, tools, max_tokens)
            except (ProviderError, OSError) as e:
                self._resting[i] = now + self.REST
                failed.append(e)
                continue
            self._resting.pop(i, None)
            return r
        if len(failed) == 1:
            raise failed[0]
        raise ProviderError("every approved model failed: "
                            + "; ".join(str(e) or type(e).__name__ for e in failed)[:500])

    def tool_result_message(self, results):
        return self.providers[0].tool_result_message(results)

    def health(self):
        return {"ok": None, "chain": [getattr(p, "model", "?") for p in self.providers]}


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
        # Inside the BAU container the model server is another container: BAU_LLM_ENDPOINT
        # points every on-machine model there (e.g. http://llm:8080).
        local = record.get("deployment") == "local" and os.environ.get("BAU_LLM_ENDPOINT")
        return LocalHTTPProvider(base_url=local or record.get("endpoint", "http://127.0.0.1:8080"),
                                 model=record.get("api_model", record["model_id"]),
                                 template_kwargs=record.get("chat_template_kwargs"))
    if kind == "openai_compat":
        env = record.get("api_key_env", "")
        key = os.environ.get(env, "") if env else ""
        if not key:
            raise PermissionError(f"{record['model_id']} needs its API key in {env or '?'}")
        return OpenAICompatProvider(base_url=record["endpoint"],
                                    model=record.get("api_model", record["model_id"]),
                                    api_key=key, chat_path=record.get("chat_path",
                                                                      "/v1/chat/completions"),
                                    extra_body=record.get("extra_body"))
    if kind == "scripted":
        return ScriptedProvider(list(record.get("script", [])))
    raise ValueError(f"unknown adapter {kind}")
