# The operations world

Built 2026-11-15 from your three reference pictures; the full art direction is
`docs/visual/VISUAL_ART_DIRECTION.md`. Checked in a browser here with sample jobs; not yet on
your own screen.

## Open it

In Jarvis, press **WORLD** at the top.
- **Zoom:** scroll on the floor; it zooms where you point.
- **Move:** drag the floor.
- **See it all again:** double-click.
- **Read a character's record:** click it.
- **Close:** **Close** or Esc.

## What you see is real

A cut-away pixel-art headquarters at night. Jarvis's glass core is in the middle, with his
console and a lounge, and the departments sit around it, each furnished for its trade:

| Department | Who works there |
|---|---|
| Research library | the researcher, and Jarvis when he researches |
| The Forge | any agent that has no room of its own |
| Testing lab | Jarvis when his autopilot tests a tool in the sandbox |
| Innovation lab | Jarvis when he scans or inspects a project |
| Studio | the producer, and Jarvis when he drafts |
| Finance, Market | no agent works here yet: they stay empty, and say so |
| Waiting for you | an agent whose job waits for your approval |
| Stopped | an agent whose job failed, was interrupted or paused |
| Delivered | an agent whose job finished in the last 24 hours |
| Headquarters lounge | an agent with nothing to do |

Every character is one of your agents (`bau agents list`), or Jarvis himself. Each is
designed for its job:
- **Jarvis:** a cape, a halo and a tablet.
- **The researcher:** a lab coat, glasses and a book.
- **The producer:** a beret, headphones and a camera.
- **Any other agent:** a hard hat and a wrench.

Where a character stands comes only from its latest job: the job store (`bau jobs`), or, for
Jarvis, his autopilot's queue (`bau autopilot`).

When that job changes, the character walks to its new room through the doors. Nothing walks
for show:
- **Working:** the character uses its tool, its own desk screen lights up, and a green panel
  above it shows its real task.
- **Waiting for you:** it raises a hand and shows "!".
- **Stopped:** it shows red crosses for eyes.
- **Done:** it holds up a green check.
- **Quiet:** if a running job has not saved a step for 30 minutes, it says "quiet N min".
- **The core:** its rings turn only while someone works, and it turns red with HOLD.
- **Reduced motion:** if it is turned on in your computer's settings, nothing moves.

Clicking a character shows its record: task, status, model, last step, cost, errors and
files made. For a running mission it also shows the exact command to stop it,
`bau mission cancel MISSION_ID`.

The world only reads: it changes nothing.
