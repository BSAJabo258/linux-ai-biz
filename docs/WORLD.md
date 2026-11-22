# The operations world

Built 2026-11-15 from your three reference pictures; the full art direction is
`docs/visual/VISUAL_ART_DIRECTION.md`. Checked in a browser here with sample jobs; not yet on
your own screen. Full screen, tabs and the agent controls added 2026-11-21, checked the same way.

## Open it

- **When Jarvis opens:** click **Open the operations world** on the first screen. It opens on
  the neon headquarters (below); **Floor** shows the floor.
- **Any time after:** click **OPERATIONS WORLD** (it glows) in the top row. While agents work
  it says how many, for example `OPERATIONS WORLD · 2 WORKING`.
- **From the laptop:** `bau station open` opens Jarvis straight on the world.

It fills the whole screen; only the talk bar stays at the bottom, so you can talk to Jarvis
from inside it. The tabs along the top take the place of the menu:

| Tab | What it does |
|---|---|
| **HQ** | The neon headquarters (below) |
| **Floor** | Every department, every agent where her work puts her |
| **Inbox** | Every card waiting for your Accept (setup, pictures, fan replies, drops, problems, new workers, delivered work), with its number. **Open** shows it in the confirm box |
| **Workstation** | Every worker with her health, her work and her controls, what just happened, and who retired. **Run a shift now** at the top |
| **Mission Control** | Mission Control, over the world |
| **Back to Jarvis** | Closes the world (or Esc) |

On the floor:
- **Zoom:** scroll on the floor; it zooms where you point.
- **Move:** drag the floor.
- **See it all again:** double-click.
- **Open an agent:** click her, or her name in the Agents panel. Her panel comes to the top.

## Running the work from an agent's panel

Click an agent and her panel shows, besides her record:
- **Health:** her number, her mood and a bar (the workstation's own, `docs/WORKSTATION.md`).
- **Needs you:** her cards: approve her as a new worker, read what she delivered, or answer
  held work. **Open**
  shows the card in the confirm box, with Accept and Not now.
- **Her work:** each task with what is happening to it: queued, approved (runs on the next
  shift), working on it now, held for you (and why), delivered (**Read what she delivered**).
  A held task has its own card under **Needs you**: Accept lets it go on (her gateway still
  stops at every post, payment or send), Not now drops it.
- **Give her work:** type what she should do, pick the kind (research, draft, review,
  organise, test, fix) and press **Give it to her**. The productivity manager approves
  low-risk work at once and says so; anything with an outside effect is held for you.
- **Run a shift now:** the next approved task runs at once, oldest first (whoever's it is).
  You see who walks to her desk, and the panel says how it ended.

Her room follows her workstation too: approved work puts her at Headquarters ("assigned"),
running work at her desk, and work for you (a report to read, a held task) in **Review:
waiting for you**. Her job log comes first when it says more.

## The neon headquarters (HQ)

Built 2026-11-20 from your picture "BAUBSA JARVIS - Virtual Operations World". The world now
opens on it; **Floor** switches to the floor below, **HQ** back. Your picture is the style,
never the data: every line is a real record, the same ones the floor reads.

- **Behind it:** a neon headquarters at night painted by the computer (a city through tall
  windows, a holographic globe, desks with their screens off, a glossy floor), without any
  words, so it can never show a status that is not true. The picture itself never moves.
- **Jarvis agents:** the roles in your picture, then your other agents, the autopilot and the
  automaton (`bau automaton`). A role BAU has no agent for (architect, developer, tester,
  coordinator) says "not set up yet". An agent shows its real state (working, waiting for
  you, failed, done, free), or "not approved" / "changed since approval" when it has nothing
  to do and you have not approved its folder. It never says "Online": no record says that.
- **System status:** Desktop (headquarters on or off, `sudo bau hq on`) and Laptop (how many
  stations are paired; whether one is connected right now is not seen from here). "All
  systems healthy" only when nothing is wrong; otherwise each problem is listed: a HOLD, the
  autopilot paused, the money machine not ready (`bau money`).
- **Current tasks:** every agent with a job, with its real state: working first, then waiting
  for you, stopped, done.
- **What We Doing Now?:** under the words, Jarvis's real task right now, or "nothing right now".
- **Under the title:** a line for today ("Tackling Tough Tasks Tuesday" only on Tuesdays,
  "Finish Strong Friday" on Fridays, and so on), from this computer's date.
- **Our virtual world:** your eight rooms, each a picture of that room from the floor with how
  many agents are in it. Click one to open it on the floor, zoomed in.
- **The women:** each character plays her animation for her real job: working, waiting for
  you, done, or idle (stopped shows a red tag). Jarvis is in the middle; the others stand in
  the order of the departments their jobs put them in (Headquarters, Research, Forge, ...,
  Review, Stopped, Delivered). When a real job moves one to another department she **walks**
  to her new place, with "→ the department" under her name, and the others step aside
  (2026-11-21). Nothing walks without a change in the records; with "reduce motion" on in
  your computer's settings, they stand still. Click one to see her record on the floor.
  Until her painted pictures exist she is shown as her floor character.

The rooms in your picture and the rooms we have. You named four of them in prompt 2 (2026-11-20):

| In your picture | Our room |
|---|---|
| HQ | Headquarters |
| Development | Development Forge (agents with no room of their own build there) |
| Research | Research library |
| Testing | Testing lab |
| Creative | Creative Studio |
| Finance | Finance Office |
| Workshop | Innovation Workshop (prototypes) |
| Operations | no clear match; Market is the eighth room |

### Painting them in the neon style

```bash
bau world portraits --style neon                       # all seven, four poses each
bau world portraits --style neon --look jarvis         # one of them
bau world portraits --style neon --look jarvis --pose working
```

Four poses each (idle, working, waiting, done), swimsuit or clubwear level, never nudity,
through the same checks as the portraits below. ComfyUI does one picture at a time and the
creator's pictures share it: on 2026-11-20 its queue held 14 of them at about 33 minutes each,
so the 28 pictures wait their turn. Not yet painted on your desktop.

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
| Development Forge | any agent that has no room of its own |
| Testing lab | Jarvis when her autopilot tests a tool in the sandbox |
| Innovation Workshop | Jarvis when she scans or inspects a project |
| Creative Studio | the producer, and Jarvis when she drafts |
| Finance Office, Market | no agent works here yet: they stay empty, and say so |
| Review: waiting for you | an agent whose job waits for your approval, or whose result failed the check (with Delivered below it, the Delivery and Review Center) |
| Stopped | an agent whose job failed, was interrupted or paused |
| Delivered | an agent whose job finished and passed the check, in the last 24 hours |
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

It paints all seven (one with `--look NAME`, again with `--again`), saying each one as it
goes; if the picture setup is not running on this computer, it says so and how to start it,
and draws nothing. Every portrait goes
through the same checks as the creator's pictures: anything about minors is refused, the age
check looks at each one and throws away any that could pass for under 20, and it is kept with
a record of how it was made. Portraits are kept in their own folder, never with the creator's
pictures, so they are never posted to Fanvue. Not yet run on your desktop.

Where a character stands comes only from its latest job: the job store (`bau jobs`), or, for
Jarvis, her autopilot's queue (`bau autopilot`).

When that job changes, the character walks to its new room through the doors. Nothing walks
for show:
- **Assigned:** a task is recorded and given to her but has not started: she waits at
  Headquarters. When it starts she walks to her department.
- **Working:** the character uses its tool, its own desk screen lights up, and a green panel
  above it shows its real task.
- **Waiting for you:** she raises a hand and shows "!".
- **Stopped:** it shows red crosses for eyes.
- **Done:** it holds up a green check.
- **Quiet:** if a running job has not saved a step for 30 minutes, it says "quiet N min".
- **The core:** its rings turn only while someone works, and it turns red with HOLD.
- **Reduced motion:** if it is turned on in your computer's settings, nothing moves.

Clicking a character shows its record: task, status, model, last step, cost, errors and
files made, and **This task, step by step**: recorded, dispatched, working, the result (with
the tools used), the check (every fact backed by what the tools returned), your review, and
delivered. Each step says done, now, waiting for you, stopped or not needed, read from the
job and its mission. The whole picture is in `docs/visual/BAUBSA-WORLD-PRODUCT-SPEC.md`. For a running mission it also shows the exact command to stop it,
`bau mission cancel MISSION_ID`.

The floor itself only shows records; what you do from the panels goes through the same
workstation, productivity manager and confirm cards as everywhere else in Jarvis.
