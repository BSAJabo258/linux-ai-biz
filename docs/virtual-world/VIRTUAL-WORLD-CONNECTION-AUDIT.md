# The virtual world's connection to Jarvis: audit (2026-11-20)

Done on the owner's desktop (headquarters) against the running system: Jarvis's live
`/api/world`, the autopilot's record, the audit chain (`/var/lib/bau/audit/chain.jsonl`), the
service logs and the code on `main` at #216. Nothing below is a guess; each finding names what
was read. The defects, their causes and fixes are in [DEFECT-REGISTER.md](DEFECT-REGISTER.md).

## The short answer

The world is **really connected, but only to part of the work**, and on the owner's desktop it
had almost nothing it could show:

1. Of the two agents installed, **neither could take work** (one approval voided by an update
   ten days ago, one never approved), so every agent character stood idle (D1).
2. **Your decisions are invisible in the world.** Picture reviews, fan replies, setup steps and
   Jarvis's questions live as cards in Jarvis's memory; the world never reads them, so it says
   "0 waiting" while two pictures wait for you (D2).
3. **Three dead jobs counted as running** after a reboot; they made Jarvis look busier than she
   was and stopped the creator feed from making pictures (D3, fixed in this change).
4. The `bau` typed in a terminal runs an **old development copy**, not the installed BAU (D4).
5. Work lives in **three task stores** and the world reads two of them (D5).

## The path, step by step

| Step | Where it really happens | Connected to the world? |
|---|---|---|
| Owner's request | Jarvis's chat (`src/bau/assistant.py`, `Assistant.ask`), `bau mission`, the workstation's ASSIGN form (`src/bau/workstation.py`) | Not from the world: `/api/world` is read-only. Requests start in the chat, the terminal or the workstation |
| Agent selection | A mission names its agent (`src/bau/jarvis.py`, `NEEDS` and the readiness check in `src/bau/agentfolders.py`, `readiness`) | The world shows the agent once its job exists |
| Executive coordinator | `jarvis.agent_executor` creates one job per run and dispatches it (`src/bau/executive.py`, `src/bau/adapters/agent_folder.py`) | Yes: the job store |
| Task record | `JobStore` (`src/bau/jobs.py`, files in `BAU_HOME/jobs/`) | Yes: `world.world()` reads every job (`src/bau/world.py`) |
| Universal Gateway | `agents.run` calls tools through the gateway (`src/bau/gateway.py`) | Indirectly: the job's tool list and steps |
| Tool or model execution | the agent's steps, recorded on its job | Yes: `tools`, `steps_done` and the lifecycle in the record card |
| Results | the job's final status and the mission report | Yes: "Result" in the lifecycle |
| Manager check | `verification` on the job (VERIFIED / FAILED / UNCHECKED) | Yes: "Checked (manager)" |
| Review and approval | `Assistant.pending`, raised by `Assistant.setup_waiting` (Fanvue pictures, fan replies, setup steps, autopilot questions), answered by `Assistant.confirm` | **No** (D2). The world's "Your review" step is inferred from the job, not read from the cards |
| Completion | mission COMPLETED, next "delivered and checked" | Yes: the character walks to Delivered |
| Back to the desk | the next poll finds no running job | Yes, but only by polling (D6) |

Jarvis's own work (the autopilot: pictures, scans, research) is a different path: tasks in
`BAU_HOME/autopilot/state.json` (`src/bau/autopilot.py`). The world shows only her latest
task, so four parallel jobs look like one (D7).

## The characters

Read live from `/api/world` on 2026-11-20:

- **Jarvis**: real. Her room and state come from her latest autopilot task (`world.py`, the
  `jarvis` record): "working, Fanvue post: weekend escape with no plans" in the Studio.
- **researcher, producer**: real agent folders (`src/bau/data/agents/`). Their state comes from
  their latest job. Both idle: "changed since approval" and "not approved" (D1).
- **architect, developer, tester, coordinator**: names on the roster with "not set up yet". No
  agent folder exists; the world says so honestly and draws no fake worker.
- **autopilot, automaton**: system rows, not characters.

Identity: a character's identity is its agent folder's name (persistent, unique per folder);
`/api/world` has no separate `id` field. The workstation (`/workstation`) has its own workers
with generations and health (`src/bau/workstation.py`), built from the same folders but kept in
its own store (D5).

## Events

There is no event stream. The page polls `/api/world` every 5 seconds and draws what the
records say at that moment (D6). What the records carry:

| Event asked for | Recorded? | Where |
|---|---|---|
| assigned | yes | job created (status PENDING / mission RUNNING) |
| accepted | no separate record | the job going RUNNING |
| started | yes | job RUNNING, `updated_at` |
| research underway, tool execution | yes, per step | job steps and `tools` |
| waiting for approval | partly | jobs waiting; **cards not read** (D2) |
| blocked | yes | job / mission PAUSED or BLOCKED with the reason |
| completed, failed | yes | job status |
| returning to the office | derived | no running job on the next poll |

## What changed in this audit (a small repair to prove D3's cause)

`src/bau/autopilot.py`: every task started now records its run (process and boot); each run
first frees running tasks whose run is gone (`autopilot.recover`), marked failed
"interrupted", audited as `autopilot.recovered`. Tasks from before the record are freed after
3 hours. Tried on a copy of the desktop's autopilot record: it freed exactly the three dead
tasks and kept the one really running. Tests in `tests/test_autopilot.py`.

## Implementation sequence (priority order)

1. **Today, by the owner** (no code): approve the researcher again after reading what changed
   (`/usr/local/bin/bau agents show researcher`, then `/usr/local/bin/bau agents approve
   researcher`), and make `bau` mean the installed BAU (D4).
2. **D2, decisions in the world**: add the waiting cards to `/api/world` (same records as
   `Assistant.pending`, nothing new), an indicator over the character the card belongs to, and
   the card itself opened from the world with Accept / Not now. Phase 3's review panel builds
   on this.
3. **D1's permanent fix**: when an update changes an approved agent folder, a setup card says
   which agent changed and shows the change; the owner's Accept approves the new version.
4. **D7**: one Jarvis helper character per running autopilot task, so parallel work is seen.
5. **D5**: the workstation's tasks become jobs in `JobStore`, so there is one task record.
6. **D6**: a small event log written where jobs and tasks change state, read by the world,
   so short steps between polls are not lost.
