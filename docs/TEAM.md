# The team: who runs the show

BAU's AI works as a small team. You name who plays each part; nothing is chosen for you.

| Part | Who (suggested) | What it does |
|---|---|---|
| **Boss** | `qwen3.5-4b`: local, free, uses tools | Runs Jarvis and the agents: plans, uses the tools, prepares actions for your click |
| **Thinker** | `qwen3-4b-heretic-content`: your local uncensored Qwen | Unfiltered ideas and blunt opinions on what it is given. Text only |
| **Specialist** | `claude-opus-5-5`: Claude, paid | On call: finishes a job the boss got stuck on, and double-checks when asked |
| **Owner** | You | Approve anything that matters |

**Why the uncensored model never holds tools:** a model with its refusals removed also
follows orders hidden in a web page, an email or a file. With tools, a stranger's text
could steer your laptop and your business. As the thinker it can say anything, but what it
says reaches you and the boss as advice, never as an instruction. It runs only on your
laptop, never gets tools or personal data, and never works on anything for children.

## Set it up

After BAU is installed, each model is downloaded, tested on your laptop and approved by
you first (see [WORKSPACES.md](WORKSPACES.md), "Getting the small models"):

```bash
bau models fetch qwen3.5-4b
bau models bench qwen3.5-4b                    # must pass before you approve it
bau set-status model qwen3.5-4b APPROVED

bau models fetch qwen3-4b-heretic-content      # runs on its own port, 8082
bau models bench qwen3-4b-heretic-content
bau set-status model qwen3-4b-heretic-content APPROVED
```

Then name the team, in one line:

```bash
bau team set --boss qwen3.5-4b --thinker qwen3-4b-heretic-content \
  --specialist claude-opus-5-5 --takeover auto
bau team show
```

To keep every model on your computer, run `bau privacy local-only` first and pick a local
specialist (for example `--specialist qwen3.5-9b`); then Claude is refused as the
specialist. See [LOCAL-ONLY.md](LOCAL-ONLY.md).

The boss also becomes the model Jarvis thinks with. Change any part later with the same
command, for example `bau team set --takeover ask`.

## When the boss gets stuck

The supervisor watches every agent job the boss runs:

- **Going round in circles:** the same tool call 3 times stops the job at once, instead of
  wasting its remaining steps.
- **Out of steps, or no answer:** same as above.
- Then the job goes to the specialist with a note of what the boss tried:
  - `--takeover auto`: the specialist takes over by itself, unless your daily usage limit
    (`bau usage limits`) is reached.
  - `--takeover ask`: the job stops and tells you; no paid model runs. Until you choose,
    BAU asks.

## Facts need a source

Every answer is checked: amounts, numbers, links and quoted words that no tool result
backs are listed as **unchecked**, so you can see what was looked up and what was not. When
you want it, Jarvis can also have the specialist double-check an answer against what the
tools found (only with `--takeover auto`, because it is a paid call).

## The score sheet

```bash
bau team score
```

For each model: jobs, finished, loops, jobs handed over, unchecked facts and cost. Over time
it shows, with real numbers, how often the boss needs help, and whether the local team is
good enough for more of the work.

## Asking the thinker

In Jarvis, ask for ideas, for example "ask the thinker how we sell more mugs". Jarvis hands
it the question and any material, and shows you its answer marked as advice.
