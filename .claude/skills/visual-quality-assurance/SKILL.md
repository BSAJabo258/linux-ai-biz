---
name: visual-quality-assurance
description: Prove a visual change to Jarvis's screen, above all the operations world, by rendering it in a real browser, taking screenshots and comparing them with the owner's references. Use before saying any visual work is done, and for "check the world", "screenshots", "does it look right".
---

# Visual quality assurance

Tests prove the data. Only a browser proves what the owner sees.

## Render it

1. Make a throwaway BAU_HOME (in your scratchpad, never the owner's) with sample jobs for
   each state:
   - running
   - waiting for approval
   - completed
   - failed
   - an autopilot task in state `running`

   Say in your report that they are samples.
2. Start Jarvis's server in Python with a fixed key (`serve(make(home), Voice(home), port,
   key=...)` as in `tests/test_world_art.py`). `bau jarvis` needs a person at a terminal.
3. With Playwright (already installed; do not install it again), open `/?k=KEY`, press a key
   to wake him, remove the setup card if one is showing, and click WORLD. Collect
   `pageerror` events: any error fails the check.

## Take these shots, every time

| Shot | How |
|---|---|
| the whole world, dark and light | `setTheme('dark')` / `setTheme('light')`, screenshot `#worldbox .box` |
| each department close up | set `W_VIEW` to 2.4x on the room's middle tile |
| the character sheet | every character, every animation, 5x, from the PNG |
| a working agent | its screen lit, its panel showing its real task |
| a walk | change a job on disk, call `loadWorld()`, screenshot after 2 s and after it arrives |
| the frame time | 60 calls of `drawWorld`; report the milliseconds per frame |

## Judge them

Look at every shot yourself and compare it with the art direction's reference table. Fail it
and fix it if any of these is true:
- a room is empty or generic;
- two characters look alike;
- a name, sign or panel covers a character;
- text is unreadable in either theme;
- something lights or moves without a record behind it;
- it looks like a dashboard.

## Report

Send the owner the shots, and say what ran (the browser, the samples, the numbers). Say
plainly that it has not been on the owner's own screen until it has.
