# The AI workstation

Open it from Jarvis (the **WORKSTATION** link) or at `/workstation` with Jarvis's key. It is an
office where each approved agent folder is a worker at a desk. When a worker finishes a job it
walks to the outbox and drops the work off; when it fails, its health drops.

Nothing on the page is invented: every worker is a real agent folder, and its health moves only
with what really happened in BAU's job logs and shifts.

## Health, death and the successor

| What happened | Health |
|---|---|
| A job or shift delivered | +8 (up to 100) |
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

Only you or the autopilot can assign work or run a shift; Jarvis's model cannot. The autopilot
runs one approved task per shift (`workstation` job, Go lane).
