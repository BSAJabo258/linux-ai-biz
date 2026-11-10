# AUTOMATON AI: architecture gap analysis (2026-11-10)

What exists, what the AUTOMATON AI prompt asks for, and the distance between them. Evidence
for every "exists" is in `CAPABILITY_MATRIX.md`.

## What the architecture already is

```
 owner ── Jarvis chat (assistant.py, 38 tools) ──┬── Universal Gateway (8 checks, audit) ── capabilities
                                                 ├── staged cards ── owner's click ── act
                                                 ├── ask_agent ── agent folder loop ── gateway
                                                 │        └── supervisor: boss -> specialist
                                                 ├── plan_mission ── policy gates ── (no executor)
                                                 └── memory / brain / chats
 autopilot timer (30 min) ── GO / VOTE / ASK lanes ── handlers ── creator feed ── Fanvue autopost
 Governor timer ── HOLD, spend, stuck jobs, services, dashboard
 God's Eye ── world data, sky themes, brand-safety hold, audience hours
 audit chain ── every action, hash-linked
```

Strong parts: the gateway, staged confirmations, the audit chain, the Governor, the creator
feed, local-first model choice, the real-model check.

## Gaps, by prompt section

| Section | Asked for | Gap | Size |
|---|---|---|---|
| 2 Execution engine | 11-step lifecycle, resumable missions | No executor runs a planned mission; jobs are not resumed; verification of Jarvis's own claims is missing | large |
| 3 Multi-agent | 10 specialists, structured messages, shared state, no loops or duplicates | One agent per request; no shared mission state; loop limit exists per agent only | large |
| 4 Governance | inspect, enforce, monitor, audit, stop, human approval | Present (gateway, Governor, audit). Missing: output validation of finished work | small |
| 5 Router | complexity, hardware, context, latency, cost, privacy, fallback, health | `route()` has most of it but is off the live path; no per-task complexity estimate | medium |
| 6 Tools | schemas, permissions, timeouts, errors, logs, verification, sandbox | Present for Jarvis and agents; no "attempted vs completed" verification per tool result | medium |
| 7 Self-improvement | generated tests, proposed fixes, isolated branches, rollback | Updates roll back; Scout sandbox-tests; Jarvis does not propose or test fixes to BAU | large |
| 8 Memory | layered, provenance, confidence, retention | Layers partly exist; no confidence score, no retention policy, failures not remembered | medium |
| 9 Mission Control | task graphs, live progress, approvals, test results, verified deliverables | No task graph or mission view; test results not shown | medium |
| 10 Content pipeline | research, plan, create, validate, package, record | Built; never produced live (Fanvue not connected) | owner step |
| 11 Benchmarks | repeatable suite, history, comparisons | Only model lab and the real-model check; no mission suite, no history | medium |

## Do not duplicate

- The executive controller already models task contracts, approval references and adapters.
  Mission execution should wire it in, not write a second controller.
- `models/router.route` already ranks models under hard constraints; the live path should
  call it, not grow `pick_model` further.
- `supervisor.unchecked` already finds unbacked facts; Jarvis-turn verification should reuse it.
- The real-model check already grades outcomes; benchmarks should extend it.
