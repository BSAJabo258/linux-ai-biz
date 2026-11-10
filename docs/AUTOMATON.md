# The automaton: make money or die

Your choice (2026-11-10): Jarvis runs the money loop **by himself**, on **$0**, and stops
himself if it does not earn.

## What it does on its own

Every 30 minutes the autopilot:

1. draws the creator's pictures on this computer (with their age check),
2. has the local model write each caption (the AI label is added to every one),
3. queues them **without** waiting for your Accept,
4. posts up to your number a day to Fanvue (autopost), in the audience's evening, and holds
   them on the day of a major disaster (God's Eye, see `docs/GODS-EYE.md`),
5. brings Fanvue's earnings into the ledger.

## Its two lines

- **Money:** it may spend what you give it from its start. With `--budget 0` (your choice)
  it uses only this computer's own models and free tools; Claude and other paid models are
  skipped while it runs. Any spending past the budget and it dies.
- **Time:** it must earn something every 30 days (`--days`). Each payment resets the clock.
  No income for 30 days and it dies.

Dying puts BAU on HOLD (only read-only actions run), switches autopost off and shows
"automaton died" in red with the reason. Only you revive it.

## What still applies, always

These are the law and Fanvue's own terms, not settings: adults 21+ only, nothing about
minors, the AI label on every post, your written explicit limits, and no cold email or texts
to people who never signed up.

## Before it can earn

1. The pictures must work (the NVIDIA CUDA library, see `docs/PICTURES.md`).
2. Fanvue must be connected once: `bau fanvue login` (see `docs/FANVUE.md`).

## Commands

```bash
bau automaton start --audience subscribers --per-day 3   # you, at a terminal
bau automaton status                                     # day, earned, spent, days left
bau automaton stop                                       # you
```

`--audience` and `--per-day` have no default: they are yours to choose. `--budget` is 0 and
`--days` is 30 unless you say otherwise. After it has died, release the HOLD
(`bau governor release`) and start it again.
