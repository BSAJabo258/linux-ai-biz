---
name: game-ui-and-world-integration
description: Connect the operations world to Jarvis's real agents and jobs, and make it interactive (zoom, move, select, inspect). Use when an agent or job type should show in the world, when characters do not move as their jobs change, for /api/world, and for "connect the world to the agents", "zoom", "click an agent".
---

# Game UI and world integration

## Where the truth comes from

`src/bau/world.py` (`/api/world`, read-only) builds every character from records:
- agent folders and the job store (`jobs/job_*.json`): the latest job by `updated_at` sets
  the room;
- Jarvis from his autopilot's queue (`autopilot/state.json`): a running task's kind sets the
  room (`JOB_ROOM`);
- HOLD from the Governor.

To show a new kind of work, map it there (`DESK` for an agent's work room, `JOB_ROOM` for
an autopilot kind), with a test in `tests/test_world.py`. Never invent a state on the page.

## On the page (`src/bau/ui/jarvis.html`, WORLD)

- `loadWorld()` reads `/api/world` every 5 seconds. On first sight a character is placed
  where it is; afterwards it walks (`path()`) only when its destination changed.
- Animation comes from the state (`W_ANIM`): working → work, waiting for you → wait,
  done → done, idle → idle, anything stopped → blocked. Walking uses walk_front or
  walk_back by direction.
- Zoom and move: `W_VIEW` (wheel zoom where you point, 1x to 3.5x; drag to move;
  double-click resets). Clicking a character inverts that view to find it.
- The panel on the right (`worldInfo`) shows the record: task, status, model, last step,
  cost, errors, files made, and the exact `bau mission cancel` command.
- Controls (2026-11-21, `workPanel`): her workstation record from `/api/world` (`rec["work"]`,
  read from the saved state only, never `W.view`, which ages workers), her cards
  (`pending[].about`), give work (`/api/workstation/assign`), run a shift, remove a held task
  (`/api/workstation/withdraw`). Every change goes through the workstation's own functions
  and the confirm box (`focusCard`); the floor's drawing still only shows records.

## Rules

- Only the files in `WORLD_ART` (`src/bau/ui/jarvis_server.py`) are served under `/world/`.
  A new asset goes in that list and in `pyproject.toml`'s package data.
- Names must not clash with the rest of the page script: `node --check` in
  `tests/test_jarvis_look.py` catches a duplicate `let` (it once caught `WORLD`).
- With reduced motion: no walking, frame 0, redraw only when data changes.
