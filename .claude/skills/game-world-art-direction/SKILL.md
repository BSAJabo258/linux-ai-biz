---
name: game-world-art-direction
description: Keep the Jarvis operations world (the WORLD view) true to the owner's reference pictures. Use before any visual change to the world, when adding a department, character or prop, and for "make it look like my pictures", "art direction", "the world looks plain".
---

# Game world art direction

The art direction is `docs/visual/VISUAL_ART_DIRECTION.md`. It is the source of truth for the
world's look; the owner's three reference pictures are described there (they are not in the
repository: their licence is unknown).

## Before you change anything visual

1. Read the art direction document, all of it.
2. Name which reference picture the change serves (1: glass HQ on a lit slab; 2: pixel robots,
   racks, floating panels; 3: a pixel office with desks and wall screens).
3. Check the change against these rules. Each one is a reason to refuse your own change:
   - **Palette:** every room keeps its colour from the table. A new room needs a new colour,
     and the colour goes in the table.
   - **Camera:** isometric 2:1 tiles (`TW`/`TH` in `src/bau/ui/jarvis.html`), back walls only.
   - **Characters:** characters come from `src/bau/ui/world/characters.png` only, never
     drawn shapes.
   - **Honesty:** nothing glows, moves or fills a room unless a record in `src/bau/world.py`
     says so. Empty departments stay empty and say who would work there.
4. If the owner sends new pictures, update the reference table first, then build.

## When you are done

Run the visual-quality-assurance skill. A change without screenshots compared to the
references is not done.

## Never

- Never replace the owner's art direction with your own taste. If two of his pictures
  disagree, name both and ask.
- Never put a picture in the repository without knowing its licence.
- Never show an agent busy, walking or finished when its record does not say so.
