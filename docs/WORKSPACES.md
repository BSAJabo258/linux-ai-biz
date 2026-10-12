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

## Which brain does each step

Each step's folder says which **brain** drafts it, in its `CONTEXT.md` under `## Brain`:

| Brain | What it is | Used for |
|---|---|---|
| `small` | a free model on your own machine | routine steps: the pitch, the storyboard, titles and tags |
| `strong` | Claude (or whatever model Jarvis thinks with) | steps that need judgement: the script, the video prompts |
| `content` | a local "uncensored" model in BAU's sealed content lane | only in workspaces you create for it; never in the kids channel |

So most steps cost nothing, and you pay for Claude only where it matters. If no small
model is approved yet, Claude does those steps too and the result says so.

See and choose which model each brain is (only you can set them):

```bash
bau ws brains                                   # what each brain is now
bau ws brains --small qwen2.5-1.5b-instruct     # the free local model
bau ws brains --strong claude-opus-5-5          # optional: Jarvis's model is the default
```

A small model's draft not good enough? Redo that step with the strong brain:

```bash
bau ws run kids-channel ep-001 --brain strong
```

Or tell Jarvis "redo that with Claude".

### Getting the small models (free, on your machine)

BAU knows these small models; each download is checked against a fixed checksum:

| Model | Size | Good for |
|---|---|---|
| `qwen3.5-4b` | 2.7 GB | the best small brain for an 8 GB laptop; can use tools |
| `qwen3.5-0.8b` | 0.5 GB | the simplest steps, when memory is short |
| `qwen2.5-1.5b-instruct` | 1.1 GB | the model the live USB offers today |

On the live USB, to make `qwen3.5-4b` the local model:

```bash
bau init                      # once after updating BAU: adds the new model records
                              # (your approvals and settings stay as they are)
bau models fetch qwen3.5-4b
sudoedit /etc/bau/llm.env     # BAU_LLM_MODEL=<the file path fetch printed>
                              # BAU_LLM_ALIAS=qwen3.5-4b
sudo systemctl restart bau-llm
bau models bench qwen3.5-4b                   # must pass before it can be approved
bau set-status model qwen3.5-4b APPROVED
bau ws brains --small qwen3.5-4b
```

The benchmark also tells you if the image's llama.cpp is too old for it: if it fails,
keep `qwen2.5-1.5b-instruct` until the next image.

### The uncensored model

`qwen3-4b-heretic-content` is a 4B model with most of its refusals removed (2.5 GB, Apache
licence; its makers' own figures: it refuses 21 of 100 test requests where the original
refuses 99, and its answers drift somewhat from the original). It runs on its own port so
it can never answer as Jarvis. Running it next to `qwen3.5-4b` uses most of 8 GB of
memory, so start it only when a content step needs it:

```bash
bau models fetch qwen3-4b-heretic-content
LD_LIBRARY_PATH=/opt/llama.cpp /opt/llama.cpp/llama-server --model <the file path> \
  --alias qwen3-4b-heretic-content --jinja --host 127.0.0.1 --port 8082 --ctx-size 8192
bau models bench qwen3-4b-heretic-content
bau set-status model qwen3-4b-heretic-content APPROVED
bau ws brains --content qwen3-4b-heretic-content
```

**The content brain is sealed off.** It is only for a model whose registry record says
`lane: content_only`, with the jobs it may do listed under `use_for` (for example scripts
or lyrics). It runs on your machine only, gets no tools and no personal data, and is
refused in any workspace with kids rules. It is never chosen for you: you name it
yourself with `bau ws brains --content MODEL` after benchmarking and approving it.

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
