# The operations world

Built 2026-11-15 from your three reference pictures (one frame takes about 2 ms to draw on a
computer's processor alone, measured in a headless browser): an isometric floor of rooms, one robot
for each of your agents. Tested in a browser here with sample jobs; not yet on your screen.

## Open it

In Jarvis, press **WORLD** at the top. Click a robot to see its record. **Close** or Esc
closes it.

## What you see is real

Every robot is one of your agents (`bau agents list`). The room it stands in comes only from
its latest job in BAU's job store, the same jobs `bau jobs` lists:

| Room | When |
|---|---|
| Research lab, Content studio, Workshop | its job is running (the researcher works in the lab, the producer in the studio, every other agent in the workshop) |
| Waiting for you | its job waits for your approval |
| Stopped | its job failed, was interrupted, paused or waits for the network |
| Delivered | its job finished in the last 24 hours |
| Available | no job, or its last one finished more than a day ago |

The building is drawn in the style of your pictures: glass rooms with lit rims on a slab with
a violet light along its foot, server racks, wall displays, desks with monitors and chairs,
plants, sofas in the lounge, shelves of finished work, a repair bench, and Jarvis's glass core
in the middle. The furniture is fixed; only what an agent is doing changes.

Only a working robot moves (a small bob), its own desk screen lights up, and a green panel
floats above it with its real task, as in your second picture. If a running job has not
saved a step for 30 minutes, the robot says "quiet N min": the job may be stuck. The core in
the middle glows while any agent works, and turns red with HOLD. With reduced motion turned on
in your computer's settings, nothing moves.

Clicking a robot shows its job: the task, status, model, last step, steps done and left,
cost, errors and files made. To stop a running mission, the panel shows the exact command:
`bau mission cancel MISSION_ID`.

The world only reads: it changes nothing.
