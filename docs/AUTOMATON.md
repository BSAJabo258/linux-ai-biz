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

## Its means: earnings it may spend, tiers, growing

Your ask (2026-11-10), after reading the open-source Conway Automaton (MIT): give it a
fighting chance, the safe way.

- **Earnings it may spend:** `--reinvest 50 --cap 20` lets it also spend half of what it
  has really earned, up to $20. Only money that is in the ledger counts.
- **Survival tiers** (from its own numbers, like Conway's): **normal** (money left: paid
  models may help), **low_compute** (no money left: this computer's models only),
  **critical** (7 days or fewer left to earn), **dead**.
- **Growing:** with `--grow-at 100`, once it has earned $100 a card asks you to raise its
  posts a day (then again at twice as much). Your Accept, never its own.

What it does not do, unlike Conway's: hold its own crypto wallet, copy itself, or edit its
own code. Your rules say money and changes are approved by a human.

Dying puts BAU on HOLD (only read-only actions run), switches autopost off and shows
"automaton died" in red with the reason. Only you revive it.

## What still applies, always

These are the law and Fanvue's own terms, not settings: adults 21+ only, nothing about
minors, the AI label on every post, your written explicit limits, and no cold email or texts
to people who never signed up.

## Before it can earn

Jarvis shows these as cards, one after the other; press Accept on each:

1. **Connect Fanvue**: Fanvue opens in the browser; sign in and press **Allow** (Fanvue's
   official connection: no app, no keys; or `bau fanvue connect`, see `docs/FANVUE.md`).
2. **Let Jarvis post to Fanvue on his own**: your audience and number a day.
3. **Start the automaton**: your days, budget, reinvest share, cap and grow-at.

The pictures must work too (the NVIDIA CUDA library, see `docs/PICTURES.md`).

## Commands

```bash
bau automaton start --audience subscribers --per-day 3   # you, at a terminal
bau automaton status                                     # day, earned, spent, days left
bau automaton stop                                       # you
bau automaton start --audience subscribers --per-day 3 --reinvest 50 --cap 20 --grow-at 100
bau automaton grow --per-day 5                           # you, once it has earned grow-at
```

`--audience` and `--per-day` have no default: they are yours to choose. `--budget` is 0 and
`--days` is 30 unless you say otherwise. After it has died, release the HOLD
(`bau governor release`) and start it again.
