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

A fourth reference came on 2026-11-20 (in the owner's Downloads, kept out of the repository
for the same reason): "BAUBSA JARVIS - Virtual Operations World", a neon cyberpunk headquarters
at night with seven glamorous women as the AI assistants, a holographic globe, a city through
tall windows and glass panels with neon edges. It is the style of the HQ view
(`docs/WORLD.md`); its text and statuses are not data and are never copied.

| # | What it shows | What we take from it |
|---|---|---|
| 4 | A neon HQ: title banner, JARVIS AGENTS (left), SYSTEM STATUS and CURRENT TASKS (right), OUR VIRTUAL WORLD room tiles (bottom left), neon script lines, a BAU BSA mug, a bottom bar; purple, cyan, pink and gold on near-black glass | the HQ view's layout and colours; the text-free `hq` scene behind it; the neon portraits (`--style neon`); every panel filled from `/api/world` only |

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

The owner's AI assistants, from his picture of 2026-11-17 (an illustration of seven women in a
neon operations office; kept out of the repository like the first three, its source and
licence unknown): glamorous adult women in glossy neon two-piece outfits with chokers,
armbands and boots, each with her own hair, skin, colours and the tool of her job
(`scripts/world_sprites.py`, sheet `src/bau/ui/world/characters.png`). High definition (the
owner, 2026-11-17: "best graphics possible"): each 96 by 132 frame is designed on a 64 by 88
grid, drawn three times bigger and smoothed down, so skin, hair and the glossy outfits are
softly shaded, the faces have eyes with irises and lashes, brows and glossy lips; then a crisp
dark outline and a neon rim light in her own colour. All are fictional adults;
none is drawn from a real person.

| Character | Who it is | Her look | What she works with |
|---|---|---|---|
| jarvis | Jarvis, her autopilot's jobs | long black hair, black and cyan, a glowing choker | a tablet with her plan |
| researcher | the researcher agent folder | dark hair in a bun, glasses, royal blue | an open book, pages turning |
| producer | the producer agent folder | long red hair, red | a camera at her eye, with a flash |
| engineer | other agents | long blonde hair, glasses, black and gold | a gold wrench |
| coordinator | other agents | long black hair, violet, violet boots | a tablet |
| analyst | other agents | big dark curls, gold | a tablet |
| architect | other agents | long platinum hair, white | a tablet |

Any agent without a look of her own gets one of the last four, always the same one for the
same name (`world.OTHER_LOOKS`). Every character has the same seven animations: idle (a
blink), walking toward you and away (four frames each), working (four frames, her own tool),
waiting for the owner (a hand up and "!"), blocked (red crosses for eyes, sparks) and done
(both hands up, a green check). Her painted portrait (`bau world portraits`, docs/WORLD.md)
shows in her record card.

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
