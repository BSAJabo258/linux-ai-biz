# AUTOMATON AI: capability matrix (2026-11-10)

Class: **A** implemented and tested, **B** implemented but untested, **C** partial, **D** designed
but not implemented, **E** missing. Level: **L0** proposed, **L1** implemented, **L2** tested,
**L3** proven live (see `CURRENT_STATE.md`).

## The nine questions

| # | Question | Answer | Class | Level | Evidence |
|---|---|---|---|---|---|
| 1 | Can the executive controller delegate and coordinate agents? | **Delegates to one agent; does not coordinate several.** Jarvis `ask_agent` runs one agent folder (`agentfolders.run` -> `agents.run`): every tool through the gateway, budget checked each step, a loop (same call 3 times) stops it, the supervisor hands a stuck job from the boss to the specialist. The executive controller (`executive.py`) is a tested prototype that nothing in the product calls. No task graph, no parallel or sequential multi-agent work | delegation A; coordination D | delegation L2 (0 live runs); executive L2, not reachable | `tests/test_executive.py`, `tests/test_orchestration.py`, `tests/test_team.py`; audit: 0 agent runs |
| 2 | Can God's Eye independently inspect and constrain execution? | **Narrowly.** It holds the day's Fanvue posts after an M7+ earthquake and keeps posts to the audience's evening. It does not inspect actions in general: that is the gateway (8 checks per call) and the Governor (HOLD, spend, stuck jobs, services) | God's Eye constraint A; general governance (gateway/governor) A | God's Eye L2 (autopost never ran live); gateway L3 (4 live refusals); governor L3 (1139 ticks) | `tests/test_godseye_business.py`, `tests/test_orchestration.py`, `tests/test_untrusted_taint.py`, `tests/test_governor.py`; live USGS read 2026-11-10 |
| 3 | Does the model router make actual decisions? | **Two routers.** The live one (`assistant.pick_model`) decides every turn: the owner's order, key present, local-only offline and on a $0 automaton, hosted failover with a 10-minute rest (`FallbackProvider`). The rich one (`models/router.route`: approval, licence, data boundary, offline, context, tools, input types, health, quality, cost, latency, scoring) is only reachable from `bau models route` | pick_model A; route() A but off the live path | pick_model L3 (every Jarvis turn); route() L2 | `tests/test_automaton.py` (local models only at $0), `tests/test_orchestration.py` (the router), `tests/test_audit_models.py` (failover) |
| 4 | Does memory survive sessions and support retrieval? | **Yes, thinly used.** MemoryLane (hash-linked Markdown records, offline BM25 search), the Second Brain vault, the chat library (SQLite FTS5). Records carry timestamps, tags and `authority: false`; no confidence score, no retention policy | C (no confidence, no retention) | L3: recall passed on the real model 3 times; 1 record in the live index, recall used 11 times | real-model check "recall finds 7pm" |
| 5 | Are tools permission-controlled? | **Yes.** Of Jarvis's 38 tools: 32 run through the gateway (registered, agent list, HOLD, level, network trust, data boundary, blast radius, budget, taint after outside content), 4 only stage a card for the owner's click, 2 meta tools (`tool_menu`, `use_tool`) re-enter the same path. Agents reach tools only through the gateway. Hands runs a command only on the owner's `y` and refuses sudo | A | L3 (4 live refusals on an untrusted network; 17 owner confirms) | `assistant._run_tool`, `tests/test_orchestration.py`, `tests/test_untrusted_taint.py` |
| 6 | Can Jarvis recover from failed tasks? | **Detects, rarely repairs.** Model failover and boss-to-specialist handover work; a refused or failed turn never breaks the page; jobs keep checkpoints and `bau recover` marks dead ones INTERRUPTED; the Governor flags stuck jobs. Nothing resumes an interrupted job, and a failed autopilot task stays failed (no diagnosis, no retry) | failover/handover A; resume and retry D | L2 | `tests/test_team.py` (supervisor), `tests/test_audit_models.py` (failover) |
| 7 | Does the testing infrastructure verify actual outcomes? | **Partly.** 1053 unit tests prove behaviour with fakes. The real-model check grades what Jarvis really did (tools used, notes on disk, audit chain) on the real model, but it is run by hand, not in CI, and its results were not kept. No benchmark history | C | real-model check L3 (run 3 times on 2026-11-10) | `.claude/skills/real-model-check/` |
| 8 | Does the chat interface connect these systems into one experience? | **Most of them.** Jarvis reaches memory, agents, mission planning, God's Eye, holds, posting, research, money and usage (38 tools), autopilot by talk-back (pause, resume, focus). It cannot reach the automaton, mission execution, the executive controller, the rich router or the Governor's findings | C | L3 (8/8 real-model check) | tool list read from `Assistant.tools` |
| 9 | Is the content pipeline progressing beyond its initial levels? | **In code and setup, not in output.** Levels 0-3 are built and tested end to end with fakes; the owner's explicit limits and prices are set, Chroma and the GPU pipeline are live. Pictures drawn: 0. Posts: 0. Revenue: $0. Fanvue is not connected | code A; output E | setup L3; production L0 | `tests/test_creator_feed.py`, `tests/test_automaton.py`; `/var/lib/bau` |

## The mission lifecycle (prompt section 2)

| Step | Status | Class | Level |
|---|---|---|---|
| RECEIVE, ANALYZE | Jarvis conversation; `plan_mission` names the type and checks the law gates | A | L3 (2 plans) |
| PLAN | `jarvis.Jarvis.plan`: steps and policy gates per mission type | A | L3 |
| DECOMPOSE | fixed steps per mission type; no task graph | C | L2 |
| DELEGATE | one agent per request (`ask_agent`) | C | L2 |
| EXECUTE | `Jarvis.run(m, executor)` exists; no executor is wired and `bau mission` has no `run` | C | L1 |
| OBSERVE | audit chain, activity events on the screen, Governor ticks | A | L3 |
| VERIFY | agents: `supervisor.unchecked` flags facts no tool result backs; Jarvis turns: none | C | L2 |
| RECOVER | see question 6 | C | L2 |
| LEARN | `remember`, Second Brain, mission retrospective | C | L2 |
| REPORT | briefing, night report, status page | A | L3 |
| Unique ID, state, timestamps, logs | missions and jobs have IDs, states, checkpoints; every action audited | A | L3 |
| Resumable after interruption | jobs checkpointed; not resumed automatically | C | L2 |

## Other prompt sections

| Area | Status | Class |
|---|---|---|
| Ten specialist agents (section 3) | agents are folders (`data/agents/`); the team has a boss, a thinker and a specialist; no executive/research/developer/debugging/testing/security/data/automation/memory/auditor set | C |
| Operation classes READ / WRITE / EXTERNAL / CRITICAL (section 4) | the gateway's six levels (READ_ONLY ... CRITICAL) plus blast radius cover them | A |
| Tamper-evident audit | hash-linked chain with `verify` (`bau audit`) | A, L3 |
| Self-testing and controlled self-improvement (section 7) | the check script, CI, nightly updates with rollback, Repo Scout sandbox tests; no generated tests or proposed fixes by Jarvis | C |
| Mission Control dashboard (section 9) | Jarvis screen and status page show real state only; no task graph or mission run view | C |
| Competitive benchmarks (section 11) | model lab measures models; no mission benchmark suite, no comparisons | E |
