# Self-modification lab

This is the layer someone might call "post-sentient": Jarvis can reason about his own source,
write a change, test it, and show it to the owner. It is still software, not a conscious
person, and it does not get to rewrite itself on a whim.

It is the owner's self-edit decision of 2026-11-11 made real: Jarvis writes fixes with tests,
the owner decides, and the safety files stay untouchable.

The rule is simple: **Jarvis proposes; the owner applies.** The model-callable tools cannot
write the repository, install a package, restart a service or run a shell.

## The loop

1. **Read and search.** `self_status`, `self_read` and `self_search` look only at
   `src/bau`, `tests` and `docs`.
2. **Propose.** `self_propose` takes the full new text of every changed file and a reason.
   It copies the repository to `BAU_HOME/selflab/sm_<id>/work`, then writes the change in
   that copy. The working repository is untouched.
3. **Test.** `self_test` shows you a card with the change first, because running the tests
   runs Jarvis's proposed code on this computer. On Accept it runs a fixed
   `python -m pytest -q` in the copy, with no keys, no tokens and no real BAU data (a bare
   environment and a throwaway home; `.env`, key and secret files are not copied). Tests default to
   the whole `tests` directory; a shorter list must stay under `tests/`.
4. **Diff.** `self_diff` shows the exact unified diff, whether the tests passed, and any
   output that was cut.
5. **The owner applies.** `self_apply` only puts a card on the owner's screen, with the
   whole diff (a change too large to show in full is refused: split it). The apply is bound
   to exactly what the card showed; a change swapped in afterwards is refused. If the owner
   presses Accept, the changed files are written into the working repository, but only if
   the tests passed and the base files have not changed since the proposal. It still needs
   an install and a service restart to go live.

## Boundaries

- Paths: `src/bau`, `tests`, `docs`; no absolute paths, `..`, symlinks or system files.
- No keys, secrets, `.env`, `.git`, approval keys or credentials.
- **Protected safety files** can be read but never changed: this lab itself, the gateway,
  governor, policy, blast radius, audit, keys, wipe gate, local-only and network rules, the
  sandbox, the AI label and claims checks, sanctions, money, the autopilot's Go/Vote/Ask
  lanes, Jarvis's tool menu and cards, the CLI, the runtime, agent-folder approval, the
  workstation's manager, missions, MCP pins, the updater, `tests/conftest.py`, and everything
  under `ui/`, `models/`, `security/`, `privacy/`, `data/policies/` and `data/regulations/`.
  A path has one spelling only (`./`, `//` and `..` are refused) and links are not followed. The list is `PROTECTED` in `selfmod.py`, and
  `self_apply` checks it again, so an edited proposal file cannot slip one in.
- At most 12 files, 200 KB each, 1 MB total.
- Existing tests are never rewritten; a proposal may add a new `tests/test_*.py` only, so the
  self-test cannot be made easier by the change it is checking.
- No shell, `pip`, `git push`, service restart, or network tool.
- Only a `human:` identity can apply. The model can never approve its own change.
- A failed, missing or stale test blocks the apply.
- Every propose, test and apply is written to the audit chain.

## Why the owner stays in the loop

A system that can silently change its own checks is no longer checked. This lab keeps the
useful part of self-improvement - reading its own code, making a patch, running the suite,
explaining the diff - while leaving the write to the owner and the live install. That is the
same rule as money, posting and agent-folder approval.

## Commands Jarvis can use

`self_status`, `self_read`, `self_search`, `self_propose`, `self_diff` (no card);
`self_test` and `self_apply` (each a card you Accept).

The live service cannot see these tools until the changed package is installed and
`bau-jarvis.service` is restarted by the owner.
