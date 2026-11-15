# Two-computer operations center: baseline (2026-11-15)

The owner handed over a directive on 2026-11-15 ("Master system quality, two-computer
architecture and virtual operations world"): the desktop as headquarters, the laptop as a
visual operations center showing a workforce of real agents, a private link between them. This
records what BAU already has for each part, what is missing, and what only the owner can decide
or test. Evidence levels as in `UPGRADE_PHASE0.md`: L0 proposed, L1 built, L2 tested, L3 proven
on the owner's machine.

## What this session could reach

- The repository on `main` at `b08bae1`, plus this branch.
- **Neither computer.** No computer folder is shared with this session (the folder list was
  empty on 2026-11-15). Nothing below about the machines themselves is verified here.

## The machines, from the owner's own reports

| | Desktop | Laptop |
|---|---|---|
| Source | `docs/DESKTOP.md` (the owner's Windows check) | `docs/HANDOFF.md`, `docs/LAPTOP-CHECK.md` |
| Memory | 16 GB | 8 GB |
| Graphics | NVIDIA RTX 3060, 12 GB | no NVIDIA card |
| State | BAU installed on the 932 GB TOSHIBA | its 1 TB install reported corrupted; it waits for a second 1 TB drive |

The directive's "12 GB RAM and 12 GB VRAM" matches neither machine exactly: the 12 GB is the
desktop's card. The laptop's present state is unknown until the owner runs the laptop check
(`installer/bau-laptop-check.sh` from the stick) and shares the summary.

## The directive against BAU

| Part | What BAU has | Level | Missing |
|---|---|---|---|
| 5 Agent manifests | agent folders: `AGENT.md` (brain, tools, mcp, skills, max_steps), owner approval tied to the folder's SHA-256 | L2 | input/output schemas, resource needs per agent |
| 5 Readiness check | **built on this branch**: `bau agents ready`, run before every mission | L2 | resource check (RAM, card memory) before a model loads |
| 6 Task lifecycle | missions (PLANNED, READY, RUNNING, COMPLETED / PAUSED / FAILED / CANCELLED), one job per run through the executive controller, verification from tool evidence | L2 | task graph: one mission split into dependent tasks for several agents |
| 7 Tool registry | `bau catalog`, `bau mcp` (Phase 2) | L2 | Jarvis cards for check, pin, revoke |
| 3 Resources | `bau hw`, the model lab, `bau hw fit` | L2, L3 for `bau hw` on the desktop | a scheduler that stops two big models loading at once |
| 4 Virtual world | the Jarvis screen: nodes light up from real activity events (`activity.py`), the AUTOPILOT panel from the real job list | L3 (screen) | a world view per agent: workstation, current job, tools, last heartbeat |
| 2 Two computers | none | L0 | everything: see the decision below |
| 10 Security | gateway (permissions, HOLD, budgets, audit), human-only approvals | L3 | authenticated computer-to-computer messages |

## Decisions only the owner can make

1. **Opening a port between the two computers.** CLAUDE.md says servers bind to this computer
   only; the one exception is the cloud server's SSH. Any link between the desktop and the
   laptop breaks that rule unless the owner allows a second exception. The smallest choice is
   the same as the cloud server's: SSH with keys only, on the home network only, and BAU's
   messages carried through it. Nothing is built until the owner decides.
2. **The laptop's drive.** Nothing formats, partitions or reinstalls it. The 128 GB stick
   belongs to the desktop and is never written to. A new install waits for the owner's word and
   the second drive.

## Order of work (smallest first, each its own pull request)

1. Readiness before a mission starts: **this branch**.
2. A resource check in readiness: is there memory for the model it needs (`bau hw`), and is
   another big model already loaded?
3. The world view on the existing Jarvis screen: one card per agent from its real job (agent,
   mission, tools, last step, status), no movement without a job state change.
4. A task graph: one mission, several dependent tasks, each verified before the next starts.
5. The two-computer link, after decision 1 and once the laptop runs again.
