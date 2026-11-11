"""MCP / tool router (spec §50-51): MCP servers are capabilities, not administrators.

A minimal Model Context Protocol client over the stdio transport (newline-delimited
JSON-RPC 2.0). Only servers whose registry record is APPROVED/ACTIVE are started.
Each tool a server exposes is registered on the Universal Gateway as its own
capability (``run.mcp__<server>__<tool>``), so permission levels, revocation,
budgets, network trust and audit all apply per tool. Tools default to
APPROVAL_REQUIRED unless the registry record explicitly marks them read-only.

The connector manager (Phase 2, 2026-11-11): ``check`` starts an approved server, lists its
tools within a time limit and records the result in ``BAU_HOME/mcp/health.json``; the owner
pins that tool list (``bau mcp pin``, its SHA-256 in the record as ``schema_sha256``). From
then on ``attach`` refuses the server whenever its tools, descriptions or input schemas
differ from the pinned list, until the owner checks and pins again.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any

from . import __version__
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
                                           "clientInfo": {"name": "bau", "version": __version__}})
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
    tools = client.list_tools()
    pinned = record.get("schema_sha256")
    if pinned and fingerprint(tools) != pinned:
        client.close()
        raise PermissionError(f"MCP server {server}'s tools changed since the owner pinned "
                              f"them: run `bau mcp check {server}`, then `bau mcp pin "
                              f"{server}` if the change is wanted")
    read_only = set(record.get("read_only_tools", []))
    allowed = record.get("tools")            # explicit allow-list from the registry
    specs: dict[str, ToolSpec] = {}
    for t in tools:
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


def fingerprint(tools: list[dict[str, Any]]) -> str:
    """SHA-256 of a server's tool list: names, descriptions and input schemas. A changed
    description matters too: it is text a model reads."""
    rows = sorted([str(t.get("name", "")), str(t.get("description") or ""),
                   t.get("inputSchema") or {}] for t in tools)
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def health_path(home: Path) -> Path:
    return home / "mcp" / "health.json"


def health(home: Path) -> dict[str, Any]:
    try:
        return json.loads(health_path(home).read_text())
    except (OSError, ValueError):
        return {}


def check(record: dict[str, Any], home: Path, client: McpClient | None = None,
          timeout: float = 30.0, audit: Any = None, actor: str = "human:owner"
          ) -> dict[str, Any]:
    """Health check of one approved server: start it, list its tools, stop it. A server that
    does not answer within ``timeout`` seconds is stopped and reported. Only approved servers
    run here; anything else is untested code and belongs in the sandbox."""
    server = record["mcp_id"]
    if record.get("status") not in ("APPROVED", "ACTIVE"):
        raise PermissionError(f"MCP server {server} is {record.get('status')}: only approved "
                              "servers are started (test others in the sandbox)")
    box: dict[str, Any] = {}

    def talk() -> None:
        try:
            c = client or McpClient(list(record["command"]), env=record.get("env"))
            box["client"] = c
            box["info"] = c.initialize()
            box["tools"] = c.list_tools()
        except Exception as e:                     # the result says what went wrong
            box["error"] = f"{type(e).__name__}: {e}"

    t = threading.Thread(target=talk, daemon=True)
    t.start()
    t.join(timeout)
    hung = t.is_alive()
    if box.get("client"):
        box["client"].close()
    t.join(5)
    if hung:                                       # stopping it made the worker fail too
        box["error"] = f"no answer within {timeout:g} s"
    tools = box.get("tools") if "error" not in box else None
    fp = fingerprint(tools) if tools is not None else None
    pinned = record.get("schema_sha256")
    res = {"at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
           "ok": tools is not None, "error": box.get("error"),
           "server": (box.get("info") or {}).get("serverInfo"),
           "tools": sorted(str(x.get("name")) for x in tools) if tools is not None else None,
           "schema_sha256": fp, "pinned": pinned,
           "changed": bool(pinned and fp and fp != pinned)}
    if tools is not None and not pinned:
        res["next"] = f"bau mcp pin {server}  (you: keep this tool list as the approved one)"
    elif res["changed"]:
        res["next"] = (f"its tools changed: BAU will not start it until you run "
                       f"`bau mcp pin {server}` (or revoke it: `bau mcp revoke {server}`)")
    allh = health(home)
    allh[server] = res
    p = health_path(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(allh, indent=1, sort_keys=True))
    tmp.replace(p)
    if audit is not None:
        audit.append("mcp.checked", actor, {"mcp_id": server, "ok": res["ok"],
                                            "changed": res["changed"], "error": res["error"]})
    return res


def pin(record: dict[str, Any], home: Path, who: str) -> dict[str, Any]:
    """The owner keeps the tool list of the last good check as the approved one."""
    server = record["mcp_id"]
    h = health(home).get(server)
    if not h or not h.get("ok") or not h.get("schema_sha256"):
        raise ValueError(f"no good check of {server} yet: run `bau mcp check {server}` first")
    return dict(record, schema_sha256=h["schema_sha256"], schema_tools=h["tools"],
                schema_pinned_by=who, schema_pinned_at=h["at"])
