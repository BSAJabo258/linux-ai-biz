---
name: character-and-sprite-production
description: Design and draw the operations world's characters as pixel-art sprite sheets (scripts/world_sprites.py). Use to add a character for a new agent, change a character's look, add an animation, or for "design the agents", "sprites", "the robots all look the same".
---

# Character and sprite production

Characters are drawn by code, so the sheet can always be rebuilt and checked:
`scripts/world_sprites.py` writes `src/bau/ui/world/characters.png` and `characters.json`.
`tests/test_world_art.py` rebuilds the sheet in memory and fails if the committed PNG differs.

## Design a character

1. **Its job first.** Name the real agent it stands for: an agent folder (`bau agents list`),
   or Jarvis himself. A character for nobody is not added.
2. **Silhouette.** Give it one shape no other character has: a hat, a cape, headphones, a
   coat. Look at the design sheet: if two characters read the same when shrunk, change one.
3. **Palette.** Add an entry to `CAST`: head, body, trim, eye, visor and limb colours, and
   `role` (one line saying what it wears and works with). Keep the outline colour `OUTLINE`.
4. **Its tool.** Add a branch to `tool()` for its `work` frames: what it holds, and how it
   changes over the four frames (a page turning, a flash, a swing).
5. **Every animation.** Every character has all seven: idle 2, walk_front 4, walk_back 4,
   work 4, wait 2, blocked 2, done 2. The test fails if one is missing.
6. **Map it.** In `src/bau/world.py`, add the agent to `LOOK` (agent name to character);
   anything unmapped uses `engineer`.

## Build and check

```bash
python3 scripts/world_sprites.py              # writes the sheet and its JSON
python3 -m pytest -q tests/test_world_art.py  # the sheet matches the script; all looks differ
```

Then make a design sheet (every character, every animation, 5x, on a dark background) with
Pillow and look at it yourself. Check that:
- arms that go up show beside the head, not behind it;
- the walking legs change between frames;
- the eyes read at 3x.

## Rules

- Frames are 32 by 44 art pixels and transparent outside the character. Nothing is
  antialiased: the page draws them with smoothing off.
- Light comes from the top left: a lighter row on top, a darker column on the right.
- Do not import sprites from elsewhere unless their licence allows business use (the owner's
  only-free-open-source rule) and the source is written in the asset table of the art
  direction document.
