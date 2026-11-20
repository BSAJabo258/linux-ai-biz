# The AI workstation

Open it from Jarvis (the **WORKSTATION** link) or at `/workstation` with Jarvis's key. It is an
office where each approved agent folder is a worker at a desk. When a worker finishes a job it
walks to the outbox and drops the work off; when it fails, its health drops.

Nothing on the page is invented: every worker is a real agent folder, and its health moves only
with what really happened in BAU's job logs and shifts.

## Waiting for you

At the top of the workstation, **Waiting for you** shows every card Jarvis holds for you, all
at once: setup steps, Jarvis's questions and new Fanvue pictures (with the picture). Each has
**Accept** and **Not now**, exactly like the card in Jarvis, and does the same thing. A card
with choices to make (prices, limits, an audience) opens in the pop-up.
Not now on a picture drops it, as in Jarvis. The list refreshes every 15 seconds.

Each new card also **pops up** over the workstation, with its picture and its choices (prices, limits, audience), so every confirm can be answered here; Accept stays locked until each choice is made. **Later** closes the pop-up and the card stays in the list.

**Tell Jarvis** (at the top) takes any request you would type in Jarvis's chat, and whatever he stages pops up at once. **FULL SCREEN** (top row) fills the screen; Esc leaves it.

## The departments at work (2026-11-20)

Four agents work for the company every day, each in its own room of the world:

| Agent | Room | Daily work | Reads |
|---|---|---|---|
| finance | Finance Office | today's earnings report | the ledger and Fanvue records (`data.money`, `data.fanvue`) |
| marketer | Market | this week's promotion plan | Fanvue activity, money, the web |
| researcher | Research library | one new legitimate way to earn, with links | memory, the web |
| producer | Creative Studio | three caption ideas for tomorrow | the Second Brain |

How it runs, with nothing new to switch on:
1. **Approve each agent once:** a card "New worker for your company" pops up (in Jarvis and
   here). Accept approves that folder exactly as it is; if an update changes it, the card
   asks again.
2. Each morning the autopilot puts each approved agent's task in its inbox; the
   productivity manager checks it (internal work only); a shift runs whenever work waits.
3. The agent walks to its room in the world and works there; every tool goes through the
   gateway; its result goes through the same fact check as a mission.
4. **Work delivered** pops up with the report: checked (every fact backed by its tools) or
   "not checked: read it carefully". Accept files it as good, Not now as not good enough.
   The full draft is in your drafts folder.

They only read and draft: no agent posts, sends, pays or signs anything.

## Health, death and the successor

| What happened | Health |
|---|---|
| A job or shift delivered **and checked** | +8 (up to 100) |
| Finished, but its result failed the check (it waits for your review) | −12 |
| A job stalled (paused, waiting) | −12 |
| A job failed or was cancelled | −25 (a failed shift −20) |
| A day without work | −4 |

Moods: thriving (80+), steady (50+), strained (25+), critical (below 25). A critical worker gets
no new work: the manager tells it to rest. At **0 health it retires** to the graveyard (nothing
is deleted), and a **successor** of the same role clocks in at 80 health. The successor takes
over every open task, carries the last six lines of its predecessor's log as a brief, and its
own manager looks at those tasks again. Each death and successor is written to the audit chain.

## The productivity manager

The manager is a fixed rule, not a person and not a model, so the workstation can run on
autopilot without a confirm card for each step. It says yes only when all of these hold:

- the work is low-risk and internal: research, draft, review, retry, continue, organise, fix,
  test;
- it does not post, publish, upload, send, pay, spend, buy, trade, delete, deploy, install,
  sign, approve, or touch money, passwords or keys;
- it says nothing about minors;
- the worker has 25 health or more;
- you have approved that agent folder once (`bau agents approve <name>`).

Anything else waits for you, exactly as before. A failed job comes back as a retry and an
interrupted one as "continue"; a job you cancelled, or one waiting for your approval, never
comes back by itself. A task that waited only because the folder was
not approved yet goes on by itself once you approve it.

## Finished is not the same as checked

A shift runs exactly like a mission: one job through the executive controller, every tool
through the gateway, then the mission's fact check (every link, quote, amount or number in
the answer must be in what the tools returned). Each job keeps three things apart:

- **COMPLETED**: the agent finished.
- **VERIFIED**: its result passed the check (the job's `verification`: VERIFIED, FAILED or
  UNCHECKED for anything that never went through it).
- **APPROVED**: you authorised it (the job's approvals).

Only checked work counts as delivered, here and in the operations world. A result that
failed the check shows as **review**: it waits for you and is never run again by itself.
Work that finished without the check earns nothing.

Only you or the autopilot can assign work or run a shift; Jarvis's model cannot. The autopilot
runs one approved task per shift (`workstation` job, Go lane).
