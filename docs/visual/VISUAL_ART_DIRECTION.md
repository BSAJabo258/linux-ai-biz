# The operations world: art direction

Written 2026-11-15 from the owner's three reference pictures, sent in the conversation that
day. The pictures themselves are not in this repository: where they came from and under what
licence is unknown (the second carries an image generator's mark), so only this description
of them is kept. Everything below is measured against them.

## The three references

| # | What it shows | What we take from it |
|---|---|---|
| 1 | An isometric cut-away of a glass headquarters on a dark slab: rooms of desks and screens around a tall glowing core, violet and blue light along the floor's edges, a night background | the camera, the slab with lit edges, glass walls with posts and lit rims, the core as the centre of the building, a dark palette lit by blue and violet |
| 2 | Pixel-art robots at work among server racks, floating green panels with text and circuits, three people at a central console | pixel-art characters, server racks, floating panels that show what is being worked on |
| 3 | A pixel-art office: robots at desks with monitors, wall screens, storage, a person in a suit in the middle | individual desks with monitors and chairs, wall displays, a tidy office floor in tiles |

## World identity

One building, seen from above at an isometric angle, cut open so every room shows. It is
night outside (dark sky with a few stars); inside, every department has its own light. The
owner names the departments (2026-11-15): the Forge, Research, Testing, Innovation, Studio,
Finance, Market, around Jarvis's headquarters.

## Camera and perspective

- Isometric 2:1: a floor tile is 112 by 56 pixels on a 1800 by 1120 canvas (`TW`, `TH` in
  `ui/jarvis.html`). The floor is 16 by 12 tiles.
- Back walls only (the cut-away): walls along each room's back edges, none in front.
- The owner zooms with the wheel (1x to 3.5x, where he points), drags to move, and
  double-clicks to see it all.

## Colour and light

| Room | Light (RGB) | Feel |
|---|---|---|
| Headquarters | 120, 160, 255 | calm blue, the core violet (169, 139, 255) |
| Research library | 63, 214, 255 | cool cyan, warm lamps |
| The Forge | 255, 140, 40 | orange, workshop |
| Testing lab | 70, 242, 164 | green, instruments |
| Innovation lab | 169, 139, 255 | violet, prototypes |
| Studio | 255, 110, 200 | magenta, stage light |
| Finance | 255, 207, 77 | gold |
| Market | 80, 220, 200 | teal |
| Waiting for you | 255, 179, 64 | amber, the owner's attention |
| Stopped | 255, 77, 94 | red |
| Delivered | 140, 200, 90 | green, finished |

Each room's floor is tinted with its light, a pool of that light sits in its middle, and its
glass walls carry the same colour on a lit rim. The slab's front edges glow violet, as in
picture 1. There is a light theme too: the same rooms on a pale floor.

## Characters

Small robots in the style of pictures 2 and 3, each one designed for its job so it can be
recognised before its card is opened (`scripts/world_sprites.py`, sheet
`src/bau/ui/world/characters.png`, 32 by 44 art pixels a frame, drawn 3x, a dark outline,
lit from the top left):

| Character | Who it is | Its look | What it works with |
|---|---|---|---|
| jarvis | Jarvis, his autopilot's jobs | violet cape with a gold hem, a gold halo, cream head | a tablet with his plan |
| researcher | the researcher agent folder | a white lab coat, round glasses, a light bulb on its antenna | an open book, pages turning |
| producer | the producer agent folder | a beret, headphones, a magenta jacket | a camera at its eye, with a flash |
| engineer | any other agent | an orange hard hat, a hi-vis vest, a tool belt | a wrench, with sparks |

Every character has the same seven animations: idle (a blink), walking toward you and away
(four frames each), working (four frames, its own tool), waiting for the owner (a hand up and
"!"), blocked (red crosses for eyes, sparks) and done (both hands up, a green check).

## Rooms and workstations

Every work department has two workstations: a desk, a chair, and the department's own
equipment. Each screen stays dark until an agent is working at it, and then shows that
department's colour.

- **Research library**: bookcases full of coloured spines, reading lamps, a book on each desk.
- **The Forge**: two monitors per desk, a server rack, a tool wall, a 3D printer with an orange bed.
- **Testing lab**: a test-results wall (green bars, one red), a meter on each desk, a cabinet.
- **Innovation lab**: a whiteboard with notes, a wireframe prototype on a pedestal.
- **Studio**: a mixing console with lit faders, a camera on a tripod, a ring light.
- **Finance**: receipts on the desks, filing cabinets, a safe.
- **Market**: stalls with goods, a sales wall.
- **Headquarters**: Jarvis's glass core with turning rings, his console, the lounge (sofas,
  a table, plants) where agents with no work wait, cabinets, a wall display.
- **Waiting for you**: two counters with a bell. **Stopped**: red repair benches with tools.
  **Delivered**: shelves of finished boxes and a conveyor.

Doors are gaps in the middle of every four tiles of an inside wall; characters walk through
them only.

## Movement and honesty

What moves is only what a real record says:

- A character stands where its latest job puts it (`src/bau/world.py`). When that job
  changes, it walks there along a path through the doors (breadth first, 2.2 tiles a
  second); on first sight it is already where it is.
- Only a working character's screen lights and its panel floats above it, with its real
  task. The core turns only while someone works, and turns red on HOLD.
- Finance and Market say "no agent works here yet": they stay empty until an agent does.
- With reduced motion turned on, nothing moves.

## Quality gates

Before a change to the world is called done, a browser renders it and the screenshots are
compared with the three pictures (`.claude/skills/visual-quality-assurance/SKILL.md`): the
whole world, each department close up, the character sheet, a working agent, and a
character walking after a real job changed. The world fails if it looks like a dashboard,
an empty room, a generic office or a row of identical placeholders.
