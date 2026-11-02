# The autopilot: Jarvis works on his own

Your ask (2026-11-02): Jarvis should work by himself, all the time, and keep growing. He
should know good from bad, vote, and keep going. He should ask you only when it matters, and
you can talk to him any time.

## What he does by himself

Every 30 minutes the autopilot works through its queue, up to 20 jobs at a time:

1. **Scan.** Once a week per topic (agents, local models, voice, video, memory and more), he
   searches GitHub with Repo Scout for the newest open-source work.
2. **Inspect.** The best finds are downloaded into quarantine and scanned. Nothing from them
   is installed or run.
3. **Sandbox test.** A find that passes inspection is queued for a test in the locked
   sandbox. That job is the next one to be built; until then, those tasks wait as
   "waiting for a handler" (`blocked` in `bau autopilot status`) and nothing is faked.
4. **Vote, then add.** Once tested, a tool goes to the vote.

Each finished job can add the next one, so the work keeps going by itself.

## Three lanes: what he may do

| Lane | What | How |
|---|---|---|
| **Go** | scan, inspect, sandbox tests, research, drafts | Just done. Logged, and in your summary |
| **Vote** | adding or enabling an ability | Two of three voters must say yes, then it's done and reported |
| **Ask you** | money, posting, legal, deleting, keys, approvals, and anything new | One question card. That job waits; everything else keeps going |

**The vote.** There are three voters:

- **The rules** can stop anything on their own. They say no to anything about minors,
  anything on the compass's never list, a licence that doesn't allow business use, and a
  tool that hasn't been tested in the sandbox.
- **The evidence:** the security scan is clean and the licence is known.
- **The judge:** the compass says it helps the business.

## The compass: his direction

`src/bau/data/autopilot_compass.yaml` says what he works toward, in your words:

- the creator's content
- growing the audience and sales
- staying sovereign and local
- a more capable Jarvis
- safety

Every job is scored against it, and the best fits go first. Its **never** list (cheats,
cracks, malware, spam bots and the like) is vetoed whatever else it scores. To change it,
copy it to `/var/lib/bau/autopilot/compass.yaml` and edit that copy, or just tell Jarvis
"focus on video".

## Talk to him

Say or type these in Jarvis:

- **"pause"** stops him starting new work.
- **"resume"** (or "carry on") starts him again.
- **"focus on video tools"** puts video tools first.
- **"what are you working on?"** gives the summary.

When he needs you, a card pops up with his question: **Accept** is yes, **Not now** is no.
The morning briefing says what he did overnight.

The same from a terminal:

```bash
bau autopilot status          # queued, done, waiting on you
bau autopilot digest          # the last 24 hours
bau autopilot questions       # what he wants to ask you
bau autopilot answer ID yes   # answer one
bau autopilot pause           # and: resume, focus WORDS, skip ID
bau autopilot run             # work now instead of waiting for the timer
```

## Turn it on

A desktop installed from a new stick has it on already. On your desktop today, Jarvis pops
up a card, **Let Jarvis work on his own**. Press Accept and type your password in the
terminal that opens.

## Built so far (2026-11-02)

**What ran:**

- The tests use fake GitHub and fake jobs: lanes, vote, compass, questions, talk-back,
  briefing, and a scan that leads to inspections and then a sandbox test.

**Not built yet:**

- The sandbox test job and the "add to Jarvis" job. Until they exist, those tasks show as
  "waiting for a handler" (`blocked` in `bau autopilot status`).
- A second AI model as the judge. Today the judge is the compass.
