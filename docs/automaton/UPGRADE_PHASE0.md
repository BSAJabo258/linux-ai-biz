# Universal automation upgrade: Phase 0 audit (2026-11-11)

The owner handed over an upgrade directive on 2026-11-11 ("BAU/BSA Jarvis: Universal
Automation, REA and Service Integration Upgrade"). Its Phase 0 asks for an audit before any
code changes. This is that audit. It builds on the AUTOMATON AI audit written on 2026-11-10
(`CURRENT_STATE.md`, `CAPABILITY_MATRIX.md`, `ARCHITECTURE_GAP_ANALYSIS.md`,
`AUTONOMOUS_EXECUTION_ROADMAP.md`) and records only what changed since or what the directive
adds. Evidence levels are the same: L0 proposed, L1 implemented, L2 tested, L3 proven live.

## Baseline

| What | Result (2026-11-11, this cloud checkout) |
|---|---|
| Code | `main` at `dd1c042`, clean working tree |
| Last eight merges | #161 to #168: pictures start after CUDA; Jarvis drafts posts; missions run (research); Jarvis sees missions; missions say what happened, web search for the researcher; Jarvis watches a video; Automaton budget and survival tiers; Governor and autopilot timers on the clock |
| `bash scripts/check.sh` | ALL PASS: lint, secrets, regulations, shellcheck (42 scripts), 1103 tests passed, 17 skipped |
| Python / Node here | 3.13.18 / 22.23.4 |
| The owner's desktop | **not audited here**: this session cannot reach it. The 2026-11-10 audit found the installed BAU older than `main`. The commands at the end of this file collect what Phase 0 needs from it |

## The directive against what already exists

| Directive part | What BAU already has | Level | What is actually missing |
|---|---|---|---|
| 9 Execution engine, lifecycle | `jarvis.Jarvis.plan/run`, `agent_executor`, Jarvis `plan_mission` and `run_mission` (research missions, checked against tool results) | L2 (run), L3 (plan) | other mission types; pause/resume as owner actions; resume after restart |
| 9 Executive controller | `executive.ExecutiveController` (task contracts, approval references, cooperative cancel, HOLD check) and `adapters/` (contract only, no real adapter) | L2, **not imported anywhere in `src/`** | wiring it under `run_mission`, with the real `jobs.JobStore` |
| 9 Jobs, checkpoints, recovery | `jobs.JobStore` (checkpoints), `jobs.recover` marks dead jobs INTERRUPTED | L2 | nothing resumes an INTERRUPTED job; failed autopilot tasks are not retried |
| 9 Multi-agent coordination | `agents.run`, agent folders, `team` (boss, thinker, specialist), `supervisor` (loop stop, handover, unbacked facts) | L2 | several agents on one mission; shared mission state; a task graph |
| 10 Model routing | live `assistant.pick_model` (L3); rich `models/router.route` | route L2, **off the live path** | calling `route()` from the live path and recording why |
| 14 Gateway and security | `gateway.py` (8 checks, audit), Governor HOLD, taint after outside content, blast radius, budgets | L3 | nothing new; every addition must go through it |
| 7 MCP | `mcp.McpClient`, `mcp.attach` registers an MCP server's tools in the gateway (read-only tools marked, others APPROVAL_REQUIRED) | L2 | discovery, health checks, schema-change detection, revocation as owner actions |
| 8 Tool catalog | toolbox (100 tools), capability map, Repo Scout (inspect in quarantine, licence and security gates), registry statuses | L2 | one record joining them, with the directive's 12 states |
| 3 REA | not present | L0 | an isolated research adapter |
| 4 Reverse API Engineer | reviewed 2026-11-08 in `docs/research/AI-BREAKTHROUGHS-LAB.md`, with rules (never on Fanvue, Instagram, TikTok; sandbox, signed out, local model) | L0 | an isolated research adapter under those rules |
| 5 Browser | Jarvis `read_page` (text only); Playwright MCP, Browser Use, agent-browser in the toolbox | read L3; acting L0 | the browser lane (`docs/research/JARVIS-AUTOMATION-ROADMAP.md` step 3) |
| 6 Desktop | Agent Desktop and Hybrid Computer Use reviewed in the roadmap and lab | L0 | the desktop lane (roadmap step 2) |
| 11 Fanvue | `fanvue.py` (OAuth PKCE, upload, post, price, earnings), creator feed levels 0-3, review cards, autopost | L2 (fakes) | an authorized real-account test (owner: `bau fanvue login`) |
| 12 Scheduling | autopilot timer, Governor timer, jobs, workspaces | L3 (timers) | dead-letter handling, webhooks |
| 13 Mission Control | Jarvis screen, status page, autopilot panel | L3 (real state only) | a mission and task-graph view |

## Outside projects the directive names (opened 2026-11-11)

| Project | Licence | What it is (its own words) | Fit for BAU | Must not |
|---|---|---|---|---|
| [morluto/rea](https://github.com/morluto/rea) | MIT | "Reverse engineer anything with agents, from app behavior down to native binaries." MCP server and CLI (`rea-agents` on npm); needs Node.js 22.x (>=22.23.4), 24.x (>=24.22.1) or 26.12.1+ | a research adapter, isolated, results untrusted | install Hopper, IDA, JEB or any engine without a free licence: REA grants no tool licence; native analysis needs "an existing Hopper, Ghidra, IDA or Kuna installation" |
| [kalil0321/reverse-api-engineer](https://github.com/kalil0321/reverse-api-engineer) | MIT (read 2026-11-08) | turns recorded browser traffic into a typed API client | a research adapter under the 2026-11-08 rules | run on Fanvue, Instagram or TikTok; commit a HAR, cookie or token |
| [microsoft/Hybrid-Computer-Use](https://github.com/microsoft/Hybrid-Computer-Use) | MIT (OSWorld files Apache-2.0) | "an open-source Model Context Protocol (MCP) server, `computer-use`"; "Linux (X11)" via "AT-SPI2, X11, XTest"; Linux binary needs Go 1.22+ | the desktop lane candidate, if the desktop session is X11 | run on the owner's signed-in desktop for untrusted tasks: its README says "Use a dedicated desktop or a disposable VM" |
| [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp) | Apache-2.0 | "A Model Context Protocol (MCP) server that provides browser automation capabilities using Playwright"; Node 18+; `--isolated` keeps the profile in memory | the browser lane candidate | use the default persistent profile; BAU starts isolated |
| [microsoft/playwright-cli](https://github.com/microsoft/playwright-cli) | Apache-2.0 | "CLI for common Playwright actions"; Node 18+; no MCP server | a compact alternative for scripted steps | - |
| [Conway-Research/automaton](https://github.com/Conway-Research/automaton) | MIT | "The first AI that can earn its own existence, replicate, and evolve"; it "generates an Ethereum wallet", can "pay with stablecoins", "can edit its own source code", and replicates by funding a child's wallet | ideas only: heartbeat, survival tiers (BAU already has them), skills | install or run it: an own wallet, self-payment, self-editing and self-replication break BAU's human-only approvals |

Already opened and recorded earlier: Agent Desktop, agent-browser, Browser Use, the MCP
registry, servers and inspector, mcp-use (all in `docs/research/AI-BREAKTHROUGHS-LAB.md` or
the toolbox, sources dated there).

## Where the directive and BAU's own rules differ

1. **n8n.** The directive allows an evaluation. BAU's licence rule (CLAUDE.md, the owner's
   rule of 2026-11-04) puts fair-code licences out, and Scout blocks them. It stays out unless
   the owner changes that rule.
2. **Docker MCP Gateway.** A second gateway would duplicate `gateway.py`; the directive itself
   says to add one only if justified. Not justified today.
3. **"Bounded automation policy" for a service.** It exists for Fanvue (autopost: the owner's
   audience and number a day, every check per post, HOLD stops it), and since 2026-11-09 every
   drafted picture waits for the owner's Accept. No new policy layer is needed; other services
   reuse the same pattern.
4. **Automatic code changes.** The directive allows Jarvis to open draft pull requests from an
   isolated branch. Nothing in BAU does this today; it needs the owner's explicit yes before
   any work starts, and merging stays the owner's.

## Duplicates and disconnected parts

- `executive.py` and `adapters/`: tested, imported by nothing in `src/`.
- `models/router.route`: tested, reachable only from `bau models route`.
- `jobs.recover`: marks INTERRUPTED, nothing resumes.
- `mcp.attach`: works per server record; there is no owner-facing way to discover, health-check
  or revoke a server from Jarvis.
- Three tool lists (toolbox, capability map, registry) with separate statuses.

None of these should be rewritten; each should be connected.

## Phase 1 plan (smallest first step, for the owner's yes)

One pull request, nothing installed:

1. `run_mission` dispatches through `ExecutiveController` with the real `jobs.JobStore`, using
   one adapter that wraps the existing `jarvis.agent_executor` (no new controller, no new job
   store).
2. Owner actions on a running mission: pause, resume, cancel (the controller's cancel already
   exists; pause/resume reuse job states).
3. After a restart, an INTERRUPTED mission job is offered back to the owner as a card to
   resume, never resumed silently.
4. Verification stays where it is: a mission is COMPLETED only when its answer holds a fact the
   tools found and none they do not back (`supervisor.unchecked`).

Tests first, with fakes: dispatch through the controller; cancel during a run; pause and
resume; restart then resume card; HOLD refuses dispatch. Proof of L3 needs the owner's desktop
after `sudo bau update now`.

Later phases keep the directive's order: tool catalog and MCP manager, then REA and Reverse API
Engineer as isolated research adapters, then the browser and desktop lanes, then multi-agent
coordination, then service adapters and Mission Control.

## What the owner runs on the desktop for the machine half of Phase 0

```bash
bau update status                       # which version is installed
python3 --version; node --version 2>/dev/null || echo "no node"
echo "$XDG_SESSION_TYPE"                # x11 or wayland (Hybrid Computer Use needs X11)
nvidia-smi --query-gpu=name,memory.total --format=csv
free -h; df -h / /home
systemctl list-timers 'bau-*' --no-pager
```

Paste the output back; it fills the machine row of the baseline.
