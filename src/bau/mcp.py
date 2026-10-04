"""MCP / tool router (spec §50-51): MCP servers are capabilities, not administrators.

A minimal Model Context Protocol client over the stdio transport (newline-delimited
JSON-RPC 2.0). Only servers whose registry record is APPROVED/ACTIVE are started.
Each tool a server exposes is registered on the Universal Gateway as its own
capability (``run.mcp__<server>__<tool>``), so permission levels, revocation,
budgets, network trust and audit all apply per tool. Tools default to
APPROVAL_REQUIRED unless the registry record explicitly marks them read-only.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from typing import Any

from .gateway import Gateway, Handler
from .models.providers import ToolSpec

PROTOCOL_VERSION = "2025-06-18"


class McpError(RuntimeError):
    pass


class McpClient:
    def __init__(self, command: list[str], env: dict[str, str] | None = None,
                 timeout: float = 60.0):
        if any(k.upper().endswith(("KEY", "TOKEN", "SECRET", "PASSWORD")) for k in env or {}):
            # Credentials reach MCP servers through the secret store, never via BAU config.
            raise PermissionError("pass MCP credentials through the secret store, not config")
        # Minimal environment: a third-party server never inherits BAU's own variables
        # (API keys, BAU_HOME, approval paths). It gets only what its record declares.
        base = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "LC_ALL", "TZ")
                if k in os.environ}
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, bufsize=1,
                                     env={**base, **(env or {})})
        self.timeout = timeout
        self._id = 0
        self._lock = threading.Lock()

    def _request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        with self._lock:
            self._id += 1
            rid = self._id
            msg = {"jsonrpc": "2.0", "id": rid, "method": method}
            if params is not None:
                msg["params"] = params
            assert self.proc.stdin and self.proc.stdout
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()
            while True:
                line = self.proc.stdout.readline()
                if not line:
                    raise McpError(f"MCP server exited during {method}")
                resp = json.loads(line)
                if resp.get("id") != rid:
                    continue            # notification or unrelated message
                if "error" in resp:
                    raise McpError(f"{method}: {resp['error'].get('message')}")
                return resp.get("result")

    def _notify(self, method: str) -> None:
        assert self.proc.stdin
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.proc.stdin.flush()

    def initialize(self) -> dict[str, Any]:
        res = self._request("initialize", {"protocolVersion": PROTOCOL_VERSION,
                                           "capabilities": {},
                                           "clientInfo": {"name": "bau", "version": "0.2"}})
        self._notify("notifications/initialized")
        return res

    def list_tools(self) -> list[dict[str, Any]]:
        tools, cursor = [], None
        while True:
            res = self._request("tools/list", {"cursor": cursor} if cursor else {})
            tools += res.get("tools", [])
            cursor = res.get("nextCursor")
            if not cursor:
                return tools

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        res = self._request("tools/call", {"name": name, "arguments": arguments})
        text = "\n".join(c.get("text", "") for c in res.get("content", [])
                         if c.get("type") == "text")
        return {"text": text, "is_error": bool(res.get("isError"))}

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def _bound_call(client: McpClient, tool: str):
    """Bind the tool name in a closure: arguments from the model can never redirect an
    approved capability to a different (unreviewed) tool."""
    def call(**kwargs: Any) -> dict[str, Any]:
        return client.call(tool, kwargs)
    return call


def attach(gateway: Gateway, record: dict[str, Any], client: McpClient | None = None
           ) -> tuple[McpClient, dict[str, ToolSpec]]:
    """Start an approved MCP server and register its tools on the gateway."""
    if record.get("status") not in ("APPROVED", "ACTIVE"):
        raise PermissionError(f"MCP server {record.get('mcp_id')} is {record.get('status')}")
    server = record["mcp_id"]
    client = client or McpClient(list(record["command"]), env=record.get("env"))
    client.initialize()
    read_only = set(record.get("read_only_tools", []))
    allowed = record.get("tools")            # explicit allow-list from the registry
    specs: dict[str, ToolSpec] = {}
    for t in client.list_tools():
        name = t["name"]
        if isinstance(allowed, list) and allowed and name not in allowed:
            continue                         # tool not reviewed: not exposed
        cap = f"run.mcp__{server}__{name}"

        fn = _bound_call(client, name)

        gateway.register(cap, Handler(fn, "READ_ONLY" if name in read_only
                                      else "APPROVAL_REQUIRED",
                                      needs_network=bool(record.get("network")),
                                      description=(t.get("description") or "")[:500]))
        specs[cap] = ToolSpec(cap, t.get("description") or name,
                              t.get("inputSchema") or {"type": "object"})
    return client, specs
