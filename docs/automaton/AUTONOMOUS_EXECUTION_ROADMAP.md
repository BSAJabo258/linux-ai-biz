# AUTOMATON AI: autonomous execution roadmap (2026-11-10)

Small, reviewable steps on a working `main`. Each step names its proof; nothing counts until
it reaches L2, and nothing is called "working" until L3 (see `CURRENT_STATE.md`).

## The five highest-impact gaps, ranked

| Rank | Gap | Impact | Depends on | Risk | Effort | Proof it is closed |
|---|---|---|---|---|---|---|
| 1 | **Jarvis says work instead of doing it** (real model, 2026-11-10: "I will draft seven posts ... Should I proceed?", no tool called) | high: talk is mistaken for work | none | low | small | real-model check 8/8 | 
| 2 | **Outcomes are not measured continuously**: the real-model check is by hand and its results are not kept; Jarvis's claims are not checked against tool results | high: without it every later step is unproven | none | low | medium | results stored per run; a claim with no backing tool result is flagged |
| 3 | **Planned missions never execute**: no executor; the executive controller is unwired; `bau mission` has no `run` | very high: the core of autonomy | 2 (to measure it), 4 (to survive failures) | medium | large | a mission plans, runs its steps through the gateway, checkpoints and reports, on the real model |
| 4 | **Recovery stops at detection**: a failed autopilot task stays failed; interrupted jobs are not resumed | high | none | medium | medium | a planted failure is retried once with its cause recorded; an interrupted job resumes |
| 5 | **The rich router is off the live path** | medium: decisions already happen in `pick_model` | 2 | low | medium | each turn records which model and why; `route()` makes the choice |

## Order

1. **Done (this change):** gap 1. The announce-without-action guard now covers making
   things (draft, plan, write, create, make, prepare, stage, queue, schedule, save, ...),
   and its nudge tells the model to say plainly when no tool fits. The creator tool's
   description now matches the code (the creator is optional when there is one profile).
   Proof: the real-model check went from 7/8 to 8/8, twice, on the desktop's `qwen3.5-9b`.
2. Gap 2: keep each real-model check result as JSON under `BAU_HOME/reports/`, add the
   "claimed but not backed" check to Jarvis turns (reuse `supervisor.unchecked`).
3. Gap 4: one retry with a recorded cause for failed autopilot tasks; resume INTERRUPTED jobs.
4. Gap 3, **first part done (2026-11-10):** a READY research mission runs (`bau mission run
   ID` at a terminal, or Jarvis's `run_mission` card on the owner's Accept): the researcher
   agent works it through the gateway, evidence is saved, and it counts as COMPLETED only
   when its answer holds at least one fact found by its tools and none they do not back;
   otherwise PAUSED with the reason. Proof on the real model: a precise mission ended
   STEP_LIMIT (PAUSED), a vague one that only found its own title PAUSED. Still open: other
   mission types (no agent carries them out), several agents on one mission (the executive
   controller), single-digit claims ("8 tools") are not checked, and the researcher has no
   web search.
5. Gap 5: call `models/router.route` from `pick_model`, record the reason per turn.

## Owner steps (not engineering)

- `sudo bau update now` puts today's merged work on the machine.
- Connect Fanvue once (`bau fanvue login`, see `docs/FANVUE.md`); until then the content
  pipeline cannot produce or earn.
