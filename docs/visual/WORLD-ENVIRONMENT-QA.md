# The world's environment: QA (2026-11-20)

The owner's prompt 2: build the world, the map and every room as a developed environment
inside the running Jarvis page. This page records what was built, the art rules it follows,
screenshots of the real page, what they show, and what still falls short. The product is
described in [BAUBSA-WORLD-PRODUCT-SPEC.md](BAUBSA-WORLD-PRODUCT-SPEC.md), the art direction in
[VISUAL_ART_DIRECTION.md](VISUAL_ART_DIRECTION.md).

## The references, checked

The owner's three original pictures from 2026-11-15 were opened again from this session's
uploads and compared with the screenshots below:

1. a glass headquarters, cut away, around a tall glowing core, violet light on the slab's edges;
2. pixel-art robots among server racks, with floating green panels;
3. a pixel-art office with desks, monitors, wall screens and storage.

The fourth (the neon HQ, 2026-11-20) is the style of the HQ view, not of this floor. None of
the pictures is in the repository (their source and licence are unknown); only their
description is kept.

## What was built

| Place | What is in it now |
|---|---|
| Headquarters | Jarvis's core and console; a **manager's post** and a **DECIDE** desk on either side of the console; the **department status board** on the back wall, one light per department, lit while an agent really works there (amber dot while one waits for you); the **INCOMING** kiosk with the real number of tasks assigned and not started; the **automaton's build pad**, drawn from its real state (dashed and dim when not started, red when dead, built up floor by floor only while it runs); the lounge (sofas, table, plants, a lamp) |
| Development Forge | three coding desks with two monitors each and a small debugging box; a code board on the wall; a build server rack with blinking lights; a task board on legs; a 3D printer; tool crates |
| Research Library | three bookcases; a pinboard of linked notes; research desks with lamps; an analysis table with papers and an open laptop; a card catalogue; a floor lamp |
| Market | a sales board and a trend board; outreach desks with headsets; a planning table; two stalls of goods |
| Creative Studio | a design desk with a drawing tablet and a mixing console; a wall of project thumbnails; an easel with a canvas; a camera on a tripod; a ring light (lit only while someone works there) |
| Innovation Workshop | a prototype on a pedestal; a bench of flasks; the sandbox, a closed glass box; a test arm on a desk; a whiteboard of notes; a tool pegboard |
| Finance Office | a ledger board and a bar chart; record cabinets; a safe; reporting desks with papers; a lamp |
| Testing lab | instruments on the desks; a test board with one red line; a trend board |
| Delivery and Review Center | Review (waiting for you) now sits directly above Delivered: a **MANAGER CHECK** desk, a **YOUR REVIEW** desk, a **REVISIONS** tray and a task board; Delivered keeps the finished-work shelves, the conveyor and an **ARCHIVE** of cabinets; one sign names the center |
| Stopped | repair benches and parts, a log board |
| The map | lit **walkways** through every doorway, the routes the agents really walk (door to door); every room keeps its light, glass walls and lit rim |

The department names are the owner's (prompt 2): Development Forge, Creative Studio,
Innovation Workshop, Finance Office. To put Review next to Delivered, the Stopped room moved
to the left side, where Review was.

Light: each room's own colour pools on its floor, wall screens glow, lamps throw warm light,
and every piece of furniture casts a soft shadow toward the front right. Ambient motion:
status lights on racks, desks, the printer and the camera blink, and the guide lights in the
walkways pulse slowly. None of it says anything about work: characters still move only when
their job changes, and with reduced motion nothing blinks.

## The art rules (technical)

| Rule | Value |
|---|---|
| Projection | isometric 2:1, seen from the front right; back walls only (the cut-away) |
| Tile | 112 by 56 pixels (`TW`, `TH`); the floor is 16 by 12 tiles; a room is 4 by 4 (HQ 8 by 4) |
| Canvas | 1800 by 1120 pixels, scaled to the window; zoom 1x to 3.5x |
| Heights | walls 84, slab 30, desks 32, monitors to 72, bookcases 104, racks 112 (pixels up) |
| Characters | a sprite sheet, 96 by 132 pixels a frame, drawn at scale 1, feet on the tile point; seven looks; `characters.png` with its map `characters.json` (`ui/world/`), rebuilt by `scripts/world_sprites.py` |
| Animation | idle 2 frames at 1.4 s, work 4 at 0.18 s, walk 4 at 0.14 s, wait, done, blocked 2 each; walking 2.2 tiles a second |
| Palette | each room's light colour (table in VISUAL_ART_DIRECTION.md); dark navy floors at night, pale floors in the light theme |
| Light | from the back left: shadows fall to the front right; room light pooled in its middle |
| Layer order | background and stars, slab, floors, walkways, walls, furniture back to front, labels, then live: blinking lights, HQ's live pieces, desk screens, characters and the core sorted by depth, task panels, room signs |
| Transparency | the sprite sheet is a PNG with transparent background; the floor is drawn, so it needs none |
| Doorways | one in the middle of every 4 tiles of each inside wall; nothing is mounted across one (a test checks it) |

The environment is drawn by code on the existing canvas, not from image files. That keeps
every desk, screen and board a real object the live layer can light up (a working agent's
own screen, the HQ board), keeps it sharp at every zoom, and costs no download. No image
generator was used: the desktop's ComfyUI is not on this test computer, and a generated
picture would be one flat image, which the owner's prompt rules out.

## Screenshots

Taken from the running page (Jarvis's own server, a real browser) in a fresh, empty home:
three agents, none working, so every desk screen is dark and the automaton says "not
started". Nothing was staged to look busy.

| # | Screenshot |
|---|---|
| 1 | [The whole map, at night](world-qa/1-map.jpg) and [in the light theme](world-qa/1-map-light.jpg) |
| 2 | [Headquarters](world-qa/2-headquarters.jpg) |
| 3 | [Development Forge](world-qa/3-forge.jpg) |
| 4 | [Research Library](world-qa/4-research.jpg) |
| 5 | [Innovation Workshop](world-qa/5-innovation.jpg) |
| 6 | [Creative Studio](world-qa/6-studio.jpg) |
| 7 | [Finance Office and Market](world-qa/7-finance-market.jpg) |
| 8 | [Delivery and Review Center](world-qa/8-delivery-review.jpg) |

The browser reported no page errors in any of them.

## What the screenshots show (inspected)

- Every department is recognisable by what is in it, without its sign.
- The map reads as one building: glass walls with doorways, and lit walkways from room to room.
- Fixed while checking: labels were hidden behind furniture drawn later (now drawn last); the
  automaton's label ran into the next room (now two short lines); several boards first sat
  across doorways, and so did the old HQ status board (all moved; a test now checks it).

## Still short of the references (honest list)

- **Detail and texture.** The references are dense, painted pixel art. This is clean blocks,
  lines and flat colour: more furniture than before, but far less texture (no wood grain,
  cables, clutter, small wall decorations).
- **Light.** There are no cast light cones or reflections on the floor, as in reference 1.
- **Characters** are unchanged; they are prompt 3.
- **Corridors** are walkways inside the rooms, through the doors; there is no separate hallway
  between departments.
- **The Testing lab and Stopped** were not in the prompt's list; they keep their place.
- **Not seen on the owner's screen yet**; these are screenshots from the test computer.
