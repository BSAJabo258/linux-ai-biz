"""Tiny MCP stdio server for tests: tools 'echo' (safe) and 'delete_all' (dangerous)."""
import json
import sys

TOOLS = [{"name": "echo", "description": "Echo text back",
          "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}},
                          "required": ["text"]}},
         {"name": "delete_all", "description": "Deletes everything",
          "inputSchema": {"type": "object"}},
         {"name": "unreviewed", "description": "Not in the allow-list",
          "inputSchema": {"type": "object"}}]

for line in sys.stdin:
    msg = json.loads(line)
    if "id" not in msg:
        continue
    m, rid = msg["method"], msg["id"]
    if m == "initialize":
        res = {"protocolVersion": msg["params"]["protocolVersion"], "capabilities": {"tools": {}},
               "serverInfo": {"name": "fake", "version": "1"}}
    elif m == "tools/list":
        res = {"tools": TOOLS}
    elif m == "tools/call":
        import os
        args = msg["params"]["arguments"]
        if args.get("text") == "__env__":
            leaked = sorted(k for k in os.environ if "KEY" in k or k.startswith("BAU_"))
            res = {"content": [{"type": "text", "text": ",".join(leaked)}]}
        else:
            res = {"content": [{"type": "text", "text": "echo: " + args.get("text", "")}]}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601,
                                                                "message": "no"}}), flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": rid, "result": res}), flush=True)
