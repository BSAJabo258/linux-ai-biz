# Workspaces: make an episode step by step

A workspace is a set of folders that holds one production line, for example a kids
channel. Each episode goes through numbered steps:

1. pitch
2. script
3. storyboard
4. video prompts
5. title and description
6. your review

Jarvis (or `bau ws run`) drafts one step at a time. **You read each draft, fix anything you
like, and check it off**; only then does the next step start, and it works from your
edited version. Everything is a plain text file you can open in any editor.

This works with any approved model, including the free Z.ai GLM-4.7-Flash
(`CLOUD-TEST.md`) or the small model on the live USB. Each step only reads the few files
it needs.

## Once: set up the channel

```bash
bau ws create kids-channel
```

Open `workspaces/kids-channel/setup/questionnaire.md` (inside your BAU folder; in a
codespace that's `/workspaces/.bau-home/workspaces/kids-channel/`). Write your answers
into `_shared/series-bible.md`, replacing every `{{...}}`. That's your channel's name,
age band, world and characters. Keep it to about a page. Steps won't run until it's
filled in.

## Every episode

```bash
bau ws episode kids-channel "Pip learns to share berries"   # start one
bau ws run kids-channel ep-001                               # draft the next step
```

Open the draft it names (`.../stages/01_pitch/output/pitch.md`), read it and edit it. When
you're happy:

```bash
bau ws check kids-channel ep-001 01
```

Then `bau ws run` again for the next step. `bau ws status kids-channel` shows every
episode and step: **checked**, **drafted** (waiting for your check), **ready**, or
**waiting**.

Or ask Jarvis: "where are my episodes?" or "draft the next step of episode 1", or press
**Draft step** on the **Producer** node of his screen. When a step is drafted, a **Waiting
for your confirmation** box pops up with the draft to read: press **Confirm** to check it,
or **Not now** to edit the file first (then **Read & check** on the Producer node brings
the box back). Jarvis can draft; only your click checks.

## What protects you

- **Kids checks:** the script, video-prompt and title steps run BAU's kids checks: no
  personal questions, links, "like and subscribe", buying pressure, scary themes, other
  companies' characters, shouting titles, or near-copies of earlier titles. You can't
  check a step while they find something. Fix the file and check again.
- **Your check is tied to what you read.** Change the file after checking it and the
  check no longer counts.
- **Step 6 is yours:** you make the video, watch it all the way through, and queue it with
  `bau youtube add ... --kids`. Uploading still waits for your `y` in `bau youtube review`.
- **Recorded:** every draft (which model, which files it read) and every check is
  recorded in BAU's tamper-evident audit log.
