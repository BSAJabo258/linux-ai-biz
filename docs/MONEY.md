# Is the money machine running?

One command tests every link from your creator to money on Fanvue, live, in the order the
money flows. It only looks; it changes nothing.

```bash
bau money
```

Each line is ✓ ready or ✗ not yet, with the exact fix under it. The last lines say what has
really happened (pictures waiting for your Accept, queued, posted, dollars received) and where
to start.

## The links, in order

| Link | Ready when | Fix |
|---|---|---|
| Creator profile | her profile file exists | `bau creator init`, then fill in her details ([VIRTUAL-CREATOR.md](VIRTUAL-CREATOR.md)) |
| Boss model | an approved model writes the captions and runs the agents | `bau team set --boss MODEL` after its benchmark ([TEAM.md](TEAM.md)) |
| Pictures | ComfyUI answers on this computer right now | `sudo systemctl start bau-pictures.service`, or the "Set up pictures" card in Jarvis |
| Fanvue app keys | the app's keys are on this computer | the "Make your Fanvue app" card in Jarvis ([FANVUE.md](FANVUE.md)) |
| Fanvue connected | you signed in and pressed Allow | `bau fanvue login` |
| Prices | your prices are in her profile | the "Set your Fanvue prices" card in Jarvis |
| Autopilot | its timer is on and you have not paused it | the "Let Jarvis work on his own" card, or `bau autopilot resume` |
| Autopost | you switched it on | `bau fanvue autopost on --audience subscribers --per-day 1` |
| No HOLD | nothing is on hold | find out why first, then `bau governor release` |

When every link is ready, the autopilot draws a picture, the boss model writes its caption,
the checks run (age, AI label, no minors), and the post waits on a card for your Accept; with
autopost on it posts by itself, up to your number a day. Earnings come back into the ledger.

## In the operations world

The world's **System status** panel shows the same score, for example "Money machine: 4 of 9
links ready. Next: Fanvue connected". The characters only move when real work happens, so a
still world with links missing means the money machine is waiting on you, not that it is
broken.

Not yet run on your desktop.
