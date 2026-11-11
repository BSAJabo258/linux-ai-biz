# Jarvis implementation map (2026-11-11)

Phase 0 of the universal automation upgrade (`docs/automaton/UPGRADE_PHASE0.md`): the real call
paths in the code, traced on `main` at `dd1c042`, with the exact places a change goes. Every
file, function and line number here was read in that commit. Line numbers drift as the code
changes: search by the function name.

## How a message becomes work today

### 1. The owner's message

```
POST /api/ask            src/bau/ui/jarvis_server.py  (handler, "/api/ask")
  -> Assistant.ask(text)  src/bau/assistant.py  (~l.1462)
       resets self.tainted; logs the message
       AUTOPILOT_CMD -> _autopilot_cmd   (pause / resume / look into / focus: no model)
       DO_ALL_CMD    -> _do_all          (stages every waiting card)
       no provider   -> _plain(text)
       else          -> _turn(text)
```

### 2. One model turn: `Assistant._turn` (~l.1530)

1. On a small local model (`self.lean`): `_ground` runs a few read tools before the model is
   asked (`GROUND` table); `RUN_MISSIONS` or a "yes" after it stages every READY mission as a
   card (`_stage_ready_missions`); a named week plan stages its card.
2. Loop, at most `max_steps` (8): `self.metered().complete(system_prompt, messages, specs)`.
   - No tool calls: the answer is final; `ANNOUNCED` + `NUDGE` push a small model that only
     announced work to actually call a tool (once).
   - Tool calls: each goes through `_run_tool`; results are wrapped by `agents.untrusted` and
     returned to the model.
3. Returns `Reply(text, cards, pending, model)`; data blocks are never read aloud.

### 3. Every tool: `Assistant._run_tool` (~l.1227)

- Unknown tool: error. Undeclared arguments are dropped.
- `kind == "confirm"`: nothing runs. A `Pending` card is staged (`jarvis.staged` audit row)
  and runs only from `Assistant.confirm` after the owner's Accept (`POST /api/confirm`).
- After outside content in this turn (`self.tainted`), "act" tools are refused
  (`jarvis.refused`).
- Tools in `self.caps` run through `Gateway.invoke(CallRequest("jarvis", cap, args,
  tainted=...))` (built in `Assistant._gateway`, ~l.382): registration, agent list, HOLD,
  level, network trust, data boundary, blast radius, budget, taint. Others run `tool.fn`
  directly and get a `jarvis.tool` audit row.

**This is the only tool path. Nothing added later may call a capability another way.**

### 4. A mission

```
plan_mission tool        Assistant.t_plan_mission  (~l.831) -> jarvis.Jarvis.plan
run_mission (confirm)    _stage_mission (card) -> owner Accept -> Assistant.confirm
                         -> Assistant.t_run_mission (~l.693)
                              Jarvis.run(m, agent_executor(...))          src/bau/jarvis.py (~l.231)
                                checks READY and governor.hold_reason
                                m.status = RUNNING, saved to jobs/missions.jsonl
                                agent_executor.execute(m)                 jarvis.py (~l.67)
                                  AGENT_FOR = {"research": "researcher"}  (the only type)
                                  agentfolders.run(name, objective, ...)  agentfolders.py (~l.252)
                                    small brain: _supervised (boss, then the specialist
                                      on takeover) -> _run_once for each; else _run_once
                                    _run_once -> agents.run(spec, task, provider, gw,
                                               JobStore(home), mission_id=...) agents.py (~l.92)
                                      creates a Job (jobs/job_*.json) unless one is passed
                                      each step: budget check, model call,
                                      gateway.invoke for every tool (~l.169)
                                  verification: supervisor.unchecked + facts backed by tools
                                COMPLETED only if verified, else PAUSED; evidence package
```

Two records describe one mission run: the mission in `jobs/missions.jsonl` (JSON lines,
latest row wins) and the agent's job in `jobs/job_*.json`. **Nothing links them**: the mission
row does not hold the job id. A supervised run with a takeover makes **two** jobs (one per
`_run_once`), so one mission can already have two unlinked jobs.

### 5. Recovery

- Boot: `bau recover` (`cli.py`, ~l.449) calls `jobs.recover(JobStore())`: RUNNING jobs become
  INTERRUPTED; network jobs wait for the network.
- Governor tick: `Governor._jobs` (`governor.py`, ~l.179) marks stale RUNNING jobs
  INTERRUPTED and, with an executor, resumes them up to `max_auto_resumes`. The CLI tick passes
  `cli_ext._resume_agent_job`, which re-runs **registry** agents only (`CapabilityRegistry
  ().data["agent"]`). Whether agent-folder agents (the researcher) are in that registry is
  **not verified**: test it before relying on it.
- Missions: `Governor._missions` reports FAILED and PAUSED missions. **A mission left RUNNING
  by a crash is never revisited.**

### 6. Parts that exist and are not connected

| Part | File | Reached from |
|---|---|---|
| `ExecutiveController`, `TaskContract`, `InMemoryJobStore` | `src/bau/executive.py` | tests only (`tests/test_executive.py`) |
| `AdapterBase`, `AdapterRegistry`, `ExecutionContext`, `ExecutionResult` | `src/bau/adapters/base.py` | tests only; no real adapter |
| `route()` | `src/bau/models/router.py` (~l.52) | `bau models route` only; the live path is `assistant.pick_model` (~l.1927) |
| `mcp.attach` | `src/bau/mcp.py` | `agentfolders.run` only (an agent folder's `mcp:` list) |

## Phase 1 work order: Jarvis executes missions through the executive controller

**Built 2026-11-11** (tests: `tests/test_mission_run.py`, `tests/test_orchestration.py`; each
safety check was removed once and its test failed). Not yet run on the owner's desktop.

Goal: one mission run goes owner -> card -> controller -> adapter -> existing agent loop ->
gateway -> verification -> back to Jarvis, with one job, linked to the mission, that can be
cancelled and is offered back after a crash. No new controller, job store, gateway or agent loop.

| Step | File and symbol | Change |
|---|---|---|
| 1 | `src/bau/agentfolders.py` `run`, `_supervised`, `_run_once` | accept `job: Job | None = None` and thread it down to `agents.run(..., job=job)`; on a takeover the specialist continues the same job (back to RUNNING) instead of creating a second. Nothing changes for callers that omit it |
| 2 | `src/bau/agents.py` `run` loop | at the top of each step, reload the job; if its status is `CANCELLED`, stop with status `CANCELLED` (today a cancel written by the controller is never seen mid-run) |
| 3 | planned new module `agent_folder` in `src/bau/adapters/`, class `AgentFolderAdapter(AdapterBase)` | `adapter_id = "agent_folder"`; `run(contract, context)` loads the controller's job and calls `agentfolders.run(contract.agent, contract.objective, ..., job=job)`; returns `ExecutionResult` with `evidence = {final_text, evidence, tool_calls, cost_usd}` and the agent's status mapped to COMPLETED / FAILED / CANCELLED |
| 4 | `src/bau/jarvis.py` `agent_executor.execute` | replace the direct `AF.run` call with `ExecutiveController(JobStore(home), registry with AgentFolderAdapter, hold=governor.hold_reason)`: `create_task(TaskContract(mission_id, objective, agent=name))`, then `dispatch(task_id, "agent_folder")`. Keep the verification code exactly as it is, fed from `result.evidence`. Return `job_id` in the result so `Jarvis.run` stores it in `m.steps["execute"]`. The `run_agent` test hook keeps working |
| 5 | `src/bau/jarvis.py` `cancel_mission`, `bau mission cancel ID` | the owner's cancel, at a terminal: `ExecutiveController.cancel` on every unfinished job of the mission, mission CANCELLED. **Changed from a Jarvis card while building:** the Jarvis screen answers one request at a time (`jarvis_server` holds its lock while a mission runs), so a card could never be pressed during a run; a terminal command is a separate process and the agent sees the cancel at its next step |
| 6 | `src/bau/governor.py` `_missions` | a mission RUNNING whose linked job is INTERRUPTED (or missing) becomes PAUSED with `next_action = "interrupted: run it again"`, so the existing PAUSED finding and the existing `run_mission` card cover it. No silent resume |

Tests first (all with fakes, in `tests/test_mission_run.py` and `tests/test_executive.py`):

1. A READY research mission run from Jarvis's card creates exactly one job, linked from the
   mission, and the agent's tool calls go through the gateway (audit rows `gateway.*`).
2. The result returns to the conversation: `t_run_mission` says COMPLETED only when verified,
   PAUSED otherwise (existing behaviour, unchanged).
3. HOLD: `dispatch` refuses; the mission ends FAILED with the HOLD reason, nothing runs.
4. Cancel during a run: the agent loop stops at its next step; job and mission are CANCELLED.
5. Crash: a RUNNING mission whose job is INTERRUPTED becomes PAUSED on the Governor tick, and
   the existing card can run it again.
6. Plant the bad case for each: remove the cancel check, see test 4 fail; remove the Governor
   change, see test 5 fail.

Commands: `python3 -m pytest -q tests/test_mission_run.py tests/test_executive.py
tests/test_orchestration.py`, then `bash scripts/check.sh` (must say ALL PASS).

Proof on the machine (L3), after `sudo bau update now` on the desktop: plan a research mission
in Jarvis, accept its run card, and read back `bau jobs` and the mission's status.

## Later phases (order from the directive, each mapped before it starts)

2. Tool catalog and MCP manager: join toolbox, capability map and registry statuses; owner
   cards to discover, health-check and revoke an MCP server (`mcp.attach` stays the only way in).
3. REA and Reverse API Engineer: research adapters, isolated, results untrusted, under the
   2026-11-08 rules.
4. Browser lane (Playwright MCP, isolated profile) and desktop lane (Hybrid Computer Use on X11,
   dedicated session), READ / FILL / DRAFT / SUBMIT as separate gateway levels.
5. Service adapters on the same contract; Fanvue's real-account test is the owner's step.
6. Mission Control: missions, jobs and their links from the records above, never sample data.
