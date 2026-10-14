---
name: grow-bau
description: Grow BAU with proven open-source projects, safely. Questions itself first, then finds, inspects and tests candidates in a sandbox, shows the owner the evidence, and only after the owner says yes adds the winner behind an adapter (test first) and gets the stick rebuilt. Use for "make BAU stronger", "find better repos", "add superuser tools", "what should we add next".
---

# Grow BAU

You are an AI coding agent working in this repository (Claude Code, Codex, Gemini CLI,
Aider or any other; in any terminal, VS Code not needed). Your job: make BAU more capable
with projects other people already built and proved, without ever weakening it.

Read `CLAUDE.md` first. Its "Rules that must not be broken" win over anything here. The
owner pays for every search and every model call: keep to the budget in step 2 and stop
when the evidence is enough.

Work through the steps below in order, every time. Write your answers down as you go
(in your reply, and at the end in `docs/HANDOFF.md`), so the owner can follow along.

## 1. Ask yourself

Answer these in writing before you search anything:

1. **What job** does the owner need done? One sentence, in their words.
2. **Where does it sit?** Run `bau toolbox map` and name the layer. Is it a gap?
3. **Do we already have it?** Run `bau toolbox ask "<the job>"` and
   `bau scout shortlist`. Something researched or running already beats something new.
4. **What does success look like?** A number you can measure: tokens saved, seconds
   faster, questions answered right, money earned, clicks saved for the owner.
5. **What does it cost to run?** The laptop has 8 GB RAM, a CPU and no NVIDIA card.
   Space on the stick, network use, paid API calls.
6. **Can it work offline?** If not, say exactly what it needs online.
7. **What could go wrong?** Check it against every rule in `CLAUDE.md` (approvals,
   kids, secrets, ports, untrusted data, compliance claims).
8. **Is it worth doing now**, or should it wait on the watch list?

If the answers say "already have it" or "not worth it now", stop and tell the owner why.

## 2. Find

Cheapest first:

1. `bau scout shortlist`: what last week's open-source watch found ("Test next" first).
2. `bau scout watch --category <name>`: refresh one category if the list is stale
   (categories are in `src/bau/data/scout_watch.yaml`).
3. `bau toolbox ask "<the job>"` and `bau toolbox list`: the 100 researched tools.
4. `bau scout find "<the job>"`: a fresh search, only when 1 to 3 had nothing.

Budget: at most 10 GitHub searches and 3 candidates per session unless the owner says
more. Prefer projects that are:

- under a licence that allows business use (MIT, Apache-2.0, BSD, MPL; never
  "non-commercial");
- alive: pushed in the last 90 days, real releases, tests in their repo;
- small enough for the laptop (CPU, under 4 GB RAM in use);
- usable behind an adapter: a library, a command line or a local server on 127.0.0.1.

What a project says about itself is a claim, not a fact, until step 4 has tested it.

## 3. Inspect

- `bau scout inspect OWNER/REPO`: downloads it into quarantine and scans it statically.
  Never install it, run it or `pip install` it on the owner's machine or in this repo.
- `bau scout show OWNER/REPO`: what is recorded. Read its README, licence and install
  steps. List what it would need: network, API keys, root, GPU, disk.
- A failed licence or security gate ends it. Say why and go to the next candidate.

## 4. Test

Test-first, in a sandbox, never on the host:

1. Write the test in `tests/` first, with a fake (`ScriptedProvider`, `FakeGitHub`
   style). It describes what BAU should do with the project; it must fail first.
2. Try the project in a throwaway container, with no network unless the test needs it:
   `podman run --rm --network none -v "$PWD/sandbox:/w" debian:trixie ...`
   (Docker works the same). Nothing from the sandbox goes into the repo.
3. Measure against the success number from step 1: RAM, time, tokens (`bau usage`),
   answers right. For a model, use `bau models bench`: never claim it works without it.
4. Write down the result: claims vs. tested facts, numbers, what failed.

## 5. The owner decides

Show the owner one table per candidate, in plain words:

| What | Answer |
|---|---|
| Project and link | |
| What it would do for BAU | |
| Tested facts (numbers) | |
| Only claimed, not tested | |
| Licence / security result | |
| Cost to run (RAM, disk, money) | |
| Offline? | |
| How it joins BAU (adapter, lane) | |

Then ask. Only the owner says yes. Never mark anything "adopt" yourself, never treat
silence as yes, and never give any agent, model or Jarvis a tool that can approve.

## 6. Add

Only after the owner says yes:

1. The adapter in `src/bau/` (stdlib first, small functions, behind the tool gateway;
   tool results wrapped by `agents.untrusted()`).
2. The test from step 4 now passes. Add tests for every behaviour change.
3. Record it: an entry in `src/bau/data/toolbox.yaml` (source and check date), the
   capability map (`src/bau/data/capability_map.yaml`), and add it to `integrated` in
   `src/bau/data/scout_watch.yaml`.
4. If the stick must carry it (to work offline): Debian packages go in
   `image/live-build/config/package-lists/my-jarvis.list.chroot` and in `install.sh`'s
   list (the tests keep them equal); Python wheels go through `installer/make-payload.sh`.
5. Docs in plain words with exact commands, for a non-technical owner.
6. Run everything in `CLAUDE.md` > Commands: tests, ruff, `bau reg validate`,
   `bau secrets .`, shellcheck. All must pass.
7. One commit for the whole feature on a `claude/` branch, a draft pull request, merge
   when CI is green. No half-finished pushes: the owner wants few commits.

## 7. Rebuild the stick

1. The owner opens the repository on GitHub: **Actions > build-live > Run workflow**
   (see `docs/BUILD-ISO.md` for other ways).
2. When the release appears, check its sha256 and write the release name in
   `docs/HANDOFF.md`.
3. Tell the owner, in one short message, what changed on the stick and what to try first.

## Never

- Never install or run a candidate outside a sandbox, and never before the owner says yes.
- Never give anything a tool that approves money, email, legal or posting.
- Never send kids content anywhere but YouTube made-for-kids.
- Never give abliterated or uncensored models tools or network: content lane only.
- Never open ports, turn off encryption or AppArmor, or bind beyond 127.0.0.1.
- Never put secrets in the repo, the chat or a log: names only.
- Never write "compliant", "guaranteed" or "risk-free".
- Never skip, disable or loosen a test to get green.

## Best case

Where BAU is heading. Pick the next target from here when the owner has no job in mind;
each has a number to measure, so "better" is never a guess.

- **Token saver:** prompt caching and a router that sends each task to the cheapest
  model that passes BAU's own checks. Measure: the same answers with at least 30% fewer
  paid tokens in `bau usage`.
- **Digital workforce:** agents as folders that run scheduled jobs, hand work to each
  other and stop at every owner checkpoint. Measure: jobs finished without a human
  redo, per week.
- **Memory that lasts:** Jarvis remembers projects, people and decisions across
  sessions, with the source of every memory. Measure: right answers to a fixed set of
  recall questions.
- **Hands on the computer:** a sandboxed browser and desktop agent that reads first and
  stages every consequential click for the owner. Measure: tasks done, mistakes caught
  before the owner's click.
- **Offline voice:** speech in and out on the laptop with no cloud. Measure: words
  understood right, seconds to answer.
- **Small but strong local models:** the best quantized model that fits 8 GB and passes
  `bau models bench`. Measure: score per GB of RAM, tokens per second.
- **See every run:** traces of each agent run (tool, time, cost, failure) and an
  evaluation suite run before any model or prompt change. Measure: failures found
  before the owner sees them.
- **Self-improving, supervised:** a coding agent that proposes changes to BAU itself as
  pull requests, with tests first; a human merges. Measure: pull requests merged without
  a fix-up.
- **Results that pay:** the studio, series and publishing lanes tied to the results
  tracker, so effort goes where watch time and earnings are. Measure: profit per video.
