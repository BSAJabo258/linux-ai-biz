---
name: environment-and-workstation-design
description: Build the operations world's rooms, departments and workstations (the static layer in src/bau/ui/jarvis.html). Use to add or change a department, furnish a room, add a workstation or prop, change doors and paths, or for "the rooms are empty", "make the Forge look like a forge".
---

# Environment and workstation design

The building is drawn once into an offscreen canvas (`drawStatic` in
`src/bau/ui/jarvis.html`) and kept; only characters, lit screens, panels and the core are
drawn every frame.

## The parts

| Part | Where |
|---|---|
| room rectangles on the 16 by 12 floor | `W_ROOMS` |
| room colours | `W_TINT` (must match the art direction's table) |
| room names and who works there | `ROOMS` in `src/bau/world.py` |
| props of each department | `roomProps(x, id, rx, ry, light)` |
| a workstation (desk, chair, the department's equipment) | `workstation(...)` |
| doors and walking | `doors()`, `blocked()`, `path()` |
| where characters stand | `SPOTS`, `spotOf()` |

## Add or change a department

1. Name the real work done there and who does it (`ROOMS`). If no agent works there yet,
   the room says so; it is not filled with fake activity.
2. Give it 3 to 5 props that only that trade has (the Forge: tool wall, 3D printer, two
   monitors per desk). A generic desk alone is not a department.
3. Keep the back row of tiles for furniture: `blocked()` keeps characters off it, except
   where a door is.
4. Never block a door: doors are in the middle of every four tiles of an inside wall
   (local column or row 2). Props must leave that tile free.
5. Draw back to front: props in a room are drawn in order of x + y.
6. Light: a room's floor tint and light pool come from `W_TINT`; a lit thing (a screen) is
   lit only in the live layer and only for a working agent (`wScreens`).

## Check

Render it (visual-quality-assurance skill), zoom on the room at 2.4x, and make sure that:
- every prop reads at that size;
- nothing hides a character's name;
- characters stand in front of their desks.
