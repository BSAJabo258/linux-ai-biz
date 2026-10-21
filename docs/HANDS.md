# Hands: Jarvis does a job in the terminal, with your yes on every step

`bau hands` lets your local model (Qwen) do a job on the computer the way a person would at
a terminal: look around, run a command, read the result, run the next one, and tell you the
answer. It follows the method of mini-swe-agent (one terminal tool, a short set of
instructions, which small models handle best), built into BAU with BAU's rules.

**Nothing runs without you.** Before every single command, you see it, Jarvis's reason, and
a plain warning when it changes or deletes things:

```
Jarvis wants to run:
  rm notes-old.txt
  (why: remove the old copy to free space)
  Careful: this changes or deletes things.
Run it? Type y and Enter (anything else: no):
```

Type `y` and Enter to run it. Anything else means no; Jarvis is told and tries another way
or stops.

## Use it

In a terminal, go to the folder the job is about, then (as yourself, **not** with sudo):

```bash
bau hands "Which file in this folder is the biggest, and how big is it?"
```

Other ideas: "List the videos in this folder by date", "How much free disk space is left?",
"Find every script that mentions episode 3". Use `--dir` to point at another folder:

```bash
bau hands "Count the episode scripts" --dir ~/Videos/kids
```

## What it will never do

- **Never root.** `sudo`, `su` and similar are refused before you are even asked, and
  `bau hands` will not start at all if you start it with sudo (then every command would have
  full power over the computer).
- **Never your approvals or keys.** BAU's approval commands, `/etc/bau` (your API keys),
  `BAU-KEYS.enc` and `.ssh` are refused before you are asked.
- **Never hidden.** Every command, your answer and the result are written to BAU's audit
  record. Output is capped and given to the model as information, never as orders.
- **Never forever.** A model that repeats the same command is stopped; a job stops after 15
  steps; each command stops after 2 minutes.

## Tested (2026-10-21)

With the Qwen3.5-4B model and the exact model server from your stick:

- "Which file in this folder is the biggest?" One command (`ls -lh`), the right answer
  (video.mp4, 3.4 MB), 39 seconds. An earlier version scanned the whole computer and got it
  wrong; the model is now told its folder and to stay in it.
- "Clear the system logs": it looked first, then asked to delete two log files. On your
  laptop that fails without sudo, and you would have seen the `rm` and could say no.
- `sudo` was never offered to the owner in any run.

Not yet tried on your laptop itself; it will be slower there than these numbers.
