# The tool catalog and MCP connectors

Built 2026-11-11 (Phase 2 of the universal automation upgrade, `docs/JARVIS_IMPLEMENTATION_MAP.md`).
Tested with fakes (`tests/test_catalog.py`); not yet run on your desktop.

## One list of every tool

BAU used to keep tools in three places: the toolbox (researched), Repo Scout (found and
inspected) and the registry (approved). The catalog reads all three and shows one record per
tool, with one state and the evidence for it.

```bash
bau catalog                       # how many tools are in each state, what is in use
bau catalog browser               # tools whose name or job mentions "browser"
bau catalog --state APPROVED      # only the approved ones
bau catalog --show microsoft/playwright-mcp   # one tool's whole record
```

In Jarvis, ask "find a tool that can fill web forms" or "which tools are approved": he uses
`tool_catalog`.

### The twelve states

A tool moves up only when BAU recorded evidence. A project's own README never moves it.

| State | What put it there |
|---|---|
| DISCOVERED | it is in the toolbox or Repo Scout found it: claims only |
| INSPECTED | Repo Scout downloaded it into quarantine and scanned it (`bau toolbox check NAME`) |
| LICENSE_VERIFIED | the licence file in that download allows business use |
| SECURITY_REVIEWED | and the scan found nothing that blocks a sandbox test |
| INSTALLED | BAU records nothing for this yet, so no tool shows it |
| CONFIGURED | an MCP server record BAU knows how to start (registry REGISTERED) |
| CONNECTED | BAU records nothing for this yet, so no tool shows it |
| TESTED | a sandbox test passed |
| APPROVED | you approved it (`bau set-status mcp ID APPROVED`) |
| ENABLED | in use: registry ACTIVE, or running in BAU (like llama.cpp) |
| DISABLED | registry DEPRECATED |
| REVOKED | you revoked it; this wins over everything else |

Anything BAU has no evidence for (a version, a cost) is left empty, never guessed.

## MCP servers (connectors)

An MCP server gives Jarvis's agents new tools. BAU starts only servers you approved, and every
tool still goes through the gateway (permissions, HOLD, budget, audit).

```bash
bau mcp list                # registered servers, their status and last check
bau mcp check ID            # start an approved server, list its tools, stop it (30 s limit)
bau mcp pin ID              # you: keep that tool list as the approved one
bau mcp revoke ID           # you: switch the server off for good
```

`pin` and `revoke` work only for a person at a terminal.

**Why pin.** A server can change after you approved it: a new tool, or a changed description
(text a model reads). Once you pin a server, BAU checks its tools every time it starts. If
anything changed, BAU refuses to start it and says so. Run `bau mcp check ID` to see the new
list, then `bau mcp pin ID` if you want it, or `bau mcp revoke ID` if not.

A server that is not approved is never started here: untested code belongs in the sandbox.
Finding new servers is Repo Scout's job (`bau scout find "mcp server for gmail"`); what it finds
shows in the catalog as DISCOVERED, and an inspected one that contains an MCP server says so in
its record.

## Not built yet

- Cards in Jarvis for check, pin and revoke: today they are terminal commands.
- Remote (network) MCP servers: BAU starts local ones only.
- Reading the official MCP Registry as a discovery source.
