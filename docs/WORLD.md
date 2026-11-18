# The operations world

Built 2026-11-15 from your three reference pictures; the full art direction is
`docs/visual/VISUAL_ART_DIRECTION.md`. Checked in a browser here with sample jobs; not yet on
your own screen.

## Open it

- **When Jarvis opens:** click **Open the operations world** on the first screen.
- **Any time after:** click **OPERATIONS WORLD** (it glows) in the top row. While agents work
  it says how many, for example `OPERATIONS WORLD · 2 WORKING`.
- **From the laptop:** `bau station open` opens Jarvis straight on the world.

Inside:
- **Zoom:** scroll on the floor; it zooms where you point.
- **Move:** drag the floor.
- **See it all again:** double-click.
- **Read a character's record:** click it, or her name in the Agents panel.
- **Close:** **Close** or Esc.

## The panels beside the floor

From your picture, filled only from real records, every 5 seconds:
- **Agents:** every agent with a light: green working, amber waiting for you, red stopped,
  grey free.
- **Current tasks:** what each working agent is doing right now, and what waits for you. If
  nothing runs it says so and how to start a mission (`bau mission list`, then
  `bau mission run ID`).
- **System status:** Jarvis running on this computer; headquarters on or off; how many laptop
  stations are paired (paired, not "connected": BAU cannot see that from here); the
  autopilot's jobs; HOLD.

## What you see is real

A cut-away pixel-art headquarters at night. Jarvis's glass core is in the middle, with his
console and a lounge, and the departments sit around it, each furnished for its trade:

| Department | Who works there |
|---|---|
| Research library | the researcher, and Jarvis when she researches |
| The Forge | any agent that has no room of its own |
| Testing lab | Jarvis when her autopilot tests a tool in the sandbox |
| Innovation lab | Jarvis when she scans or inspects a project |
| Studio | the producer, and Jarvis when she drafts |
| Finance, Market | no agent works here yet: they stay empty, and say so |
| Waiting for you | an agent whose job waits for your approval |
| Stopped | an agent whose job failed, was interrupted or paused |
| Delivered | an agent whose job finished in the last 24 hours |
| Headquarters lounge | an agent with nothing to do |

Every character is one of your agents (`bau agents list`), or Jarvis herself. Since
2026-11-17 they are drawn from your picture of your AI assistants: glamorous adult women in
glossy neon two-pieces, with chokers, armbands and boots, each with her own look and the tool
of her job:
- **Jarvis:** long black hair, black and cyan, a glowing choker and a tablet.
- **The researcher:** dark hair in a bun, glasses, royal blue, and a book.
- **The producer:** long red hair, red, and a camera.
- **Any other agent** gets one of four more looks, always the same one for the same agent:
  blonde with glasses in black and gold (a gold wrench), black hair in violet, dark curls in
  gold, or platinum hair in white (each with a tablet).

All of them are fictional adults; none is drawn from a real person.

## Painted portraits

Click a character and her record shows a large painted portrait in the style of your picture,
once it has been drawn. They are drawn on the desktop by its own picture setup (ComfyUI,
`docs/PICTURES.md`), once:

```bash
bau world portraits
```

It paints all seven (one with `--look NAME`, again with `--again`). Every portrait goes
through the same checks as the creator's pictures: anything about minors is refused, the age
check looks at each one and throws away any that could pass for under 20, and it is kept with
a record of how it was made. Portraits are kept in their own folder, never with the creator's
pictures, so they are never posted to Fanvue. Not yet run on your desktop.

Where a character stands comes only from its latest job: the job store (`bau jobs`), or, for
Jarvis, her autopilot's queue (`bau autopilot`).

When that job changes, the character walks to its new room through the doors. Nothing walks
for show:
- **Working:** the character uses its tool, its own desk screen lights up, and a green panel
  above it shows its real task.
- **Waiting for you:** she raises a hand and shows "!".
- **Stopped:** it shows red crosses for eyes.
- **Done:** it holds up a green check.
- **Quiet:** if a running job has not saved a step for 30 minutes, it says "quiet N min".
- **The core:** its rings turn only while someone works, and it turns red with HOLD.
- **Reduced motion:** if it is turned on in your computer's settings, nothing moves.

Clicking a character shows its record: task, status, model, last step, cost, errors and
files made. For a running mission it also shows the exact command to stop it,
`bau mission cancel MISSION_ID`.

The world only reads: it changes nothing.
