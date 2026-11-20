# BAUBSA operations world: the product, as built (2026-11-20)

The owner's picture (2026-11-19): open Jarvis and see a living business world, Headquarters
in the middle and the departments around it, where every character is a real agent and every
movement is real work. The world shows the business; it never acts out work that is not
happening.

This page says what is built and running today, how each thing on the screen is tied to the
real system, and what is still to build. Anything not built is in
[Not built yet](#not-built-yet). How to use the world is in [WORLD.md](../WORLD.md); its art
direction is in [VISUAL_ART_DIRECTION.md](VISUAL_ART_DIRECTION.md).

## The one rule

Every character, room, light and step on the screen comes from a real record: the job store
(`jobs/`), the mission store (`jobs/missions.jsonl`), the agent folders, the autopilot's
queue and HOLD. The world only reads (`/api/world`); it starts, changes and approves nothing.
When a record does not say something, the world does not show it.

## Where it runs

| Computer | Its part |
|---|---|
| Desktop (headquarters) | Jarvis, the agents, the models, the job and mission stores, and the world's page itself (`bau-jarvis.service`) |
| Laptop (station) | shows the desktop's world through the SSH tunnel (`bau station open`, the **Jarvis HQ** menu entry); runs no agents of its own |

The laptop is a window onto the desktop, so both always show the same records.

## The map

A cut-away headquarters, seen from above at an angle, with doors between the rooms:

| Room | Who is there, and why |
|---|---|
| Headquarters | Jarvis's core and console. An agent with nothing to do waits in its lounge; a task recorded but not started puts its agent here as **assigned** |
| Research library | the researcher while her job runs, and Jarvis when her autopilot researches |
| Studio | the producer while her job runs, and Jarvis when she drafts |
| The Forge | any agent without a desk of its own, while its job runs |
| Testing lab | Jarvis when her autopilot tests a tool in the sandbox |
| Innovation lab | Jarvis when her autopilot scans or inspects a project |
| Finance, Market | built and furnished; no agent works there yet, so they stay empty |
| Waiting for you | an agent whose job waits for your approval, or whose result failed the check |
| Stopped | an agent whose job failed, was interrupted or paused |
| Delivered | an agent whose job finished and passed the check, for 24 hours |

## One task's life, as the world shows it

The steps below are the real path of a mission (`bau mission run`, or Jarvis's
`run_mission`) and of a workstation shift. The character moves only when the job behind it
moves; the record card lists the steps, each marked done, now, waiting for you, stopped or not
needed (`world.lifecycle`).

| Step | What really happens | What you see |
|---|---|---|
| Recorded | the mission is planned; the executive controller writes a job with its ID (`jarvis.run_checked`) | the agent at Headquarters, **assigned**, "Dispatched: now" |
| Dispatched | the job starts (RUNNING) | she walks from Headquarters through the doors to her desk |
| Working | the agent folder runs on the boss model; every tool call goes through the Universal Gateway onto the audit chain | she uses her tool, her desk screen lights up, a panel shows her real task |
| Result | the agent finishes (COMPLETED), with the tools it used | "Result: done", with the tools named |
| Checked (manager) | a fixed rule, not a model: every link, quote, amount or number in the answer must be in what the tools returned (`jarvis.check_result`), recorded as the job's `verification` | "Checked: done" or "stopped" with the fact no tool backs |
| Your review | a failed check pauses the mission for you; work with an outside effect (posting, money) always waits for your Accept | she stands in **Waiting for you**; "Your review: waiting" |
| Delivered | checked work goes into the mission's report | she walks to **Delivered** with a green check |

Back to available: once her latest job is older than 24 hours she returns to the
Headquarters lounge. With no job at all she waits there; she is never shown busy.

## The characters

Each is one of the owner's agents, drawn by code as a glamorous adult woman from the owner's
picture (2026-11-17), with her own look and tool: Jarvis, the researcher, the producer, and
four more looks for any other agent. Seven animations each (idle, walking, working, waiting,
stopped, done, and the walk between rooms). Painted portraits in the record card are drawn on
the desktop's own picture setup. All are fictional adults.

## Proven

On 2026-11-20 one real research task went through the whole slice, on the real local model
(`qwen3.5-4b`, the stick's llama.cpp build) and the real private search service, with
screenshots of the running page at each stage. The evidence is in
[WORLD-SLICE-EVIDENCE.md](WORLD-SLICE-EVIDENCE.md). Not yet on the owner's own screen.

## Not built yet

What the owner's specification asks for that this world does not do yet, in the order of the
owner's prompts 2 to 5:

- **Managers as characters.** Today the manager is the fixed check rule and the
  workstation's fixed-rule manager; no manager character walks or reviews on screen.
- **Automaton on the floor.** The automaton runs (`bau automaton`) but has no place or
  character in the world.
- **The preparing walk.** No trip to an equipment station before work: the records do not
  say when an agent gathers its tools.
- **Several agents on one task**, dependencies and hand-offs between agents: one agent per
  task today.
- **Approve, reject or ask for changes from the world.** Your review is shown; the actions
  are at a terminal or on Jarvis's cards, not yet in the world's Review Center.
- **Panels:** an agent directory, a task board by state, department views, a tools view and a
  history view, all from the same records (today: Agents, Current tasks, System status).
- **Agents of their own** in Finance, Market, Testing and Innovation (today only Jarvis's
  autopilot uses Testing and Innovation).
- **Art:** the rooms are drawn by code in one style; the owner's prompt 2 asks for a richer,
  hand-made pixel-art environment (lighting, props, ambient animation) per room.
