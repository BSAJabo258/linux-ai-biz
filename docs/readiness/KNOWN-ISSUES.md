# Known issues (2026-11-18)

Every issue the readiness audit found, by priority. Evidence for each is in
[FEATURE-INVENTORY.md](FEATURE-INVENTORY.md).

| Priority | Meaning |
|---|---|
| **P0** | stops the application from starting, reaching core functions, or operating safely |
| **P1** | breaks a major product feature or real task execution |
| **P2** | important functionality, reliability or usability problem |
| **P3** | improvement for later |

## P0

**None open in the code.** A fresh install starts. Jarvis, the gateway, the audit chain, memory
and missions ran on a real local model. The safety rules held in every run: approvals stayed
human-only, posting stayed staged, and unbacked claims were stopped.

One P0 is the owner's to clear on the desktop. It still runs an older BAU, and its Jarvis
service file predates the restart limit in #189. Fix, at the desktop:

```bash
sudo bau update now
sudo bau hq on          # rewrites the Jarvis service file with the restart limit
bau selftest
```

## P1

| # | Issue | Evidence | Fix |
|---|---|---|---|
| 1 | **The money machine has never produced anything**: 0 pictures, 0 posts, $0 | desktop 11-10; the Fanvue sign-in was refused twice | owner: register `http://127.0.0.1:3456/callback` in the Fanvue app and run `bau fanvue login`. If refused again, finish #169 (Fanvue's official connection, no app keys). Then `bau money` on the desktop and follow its first fix |
| 2 | **Only 1 of 10 mission types can run**: `research` has an agent; publishing, email, subscriptions, the automation service and the rest answer "no agent carries out ... missions yet" | `AGENT_FOR` in `src/bau/jarvis.py` | give each sellable mission type an agent folder with a readiness need (Prompt 2/4) |
| 3 | **The job record says COMPLETED when the mission is PAUSED**, and it records `model: null`, `tools: []` although the model and `search.web` were used. The operations world reads it and shows the work as Delivered | the soy-wax mission, job `job_2d27bf110335` | set the job's final state from the verification result, and record the model and tools the run used |
| 4 | **The release checklist is RED**: 22 critical items not done, and 25 red items in `bau status` (regulation records past their review date, counsel review, email DNS, tax nexus, boot test) | `bau status`, `src/bau/data/build_state.yaml` | a per-item plan: what the owner verifies on the machine, and what needs counsel or a CPA. Nothing can be claimed to customers until then |
| 5 | **Local voice cannot be reinstalled**: `bau-voice` runs on the desktop but no script or doc in the repository sets it up (the code names a voice guide, VOICE.md, that does not exist) | `src/bau/assistant.py` (`Voice`) | write the setup script and doc from what runs on the desktop |
| 6 | **The laptop station is not installed or proven** on hardware, and the network between the two computers is not proven | the owner's install is pending | install from the stick onto the WD disk, then follow `docs/LAPTOP-STATION.md` |

## P2

| # | Issue | Evidence |
|---|---|---|
| 1 | **Slow on a processor**: 7 s to 4 min per answer, and 7.7 min for a research mission, on 3 cores. The desktop's card should be faster, but that is not measured for these jobs | real-model check; mission run |
| 2 | **A small model says wrong things in places**: "I cannot create workspaces yet" (`bau ws` can), and "That reminder is already stored" for a note it had just saved | real-model check transcript |
| 3 | **Search results with broken addresses reach the model** (`http:///go/...`). `read_page` refuses them, but the model still sees them | SearXNG result for a real query |
| 4 | **Two agents only, neither approved on the desktop**; 0 agent runs there as of 11-10 | `bau agents list`; desktop 11-10 |
| 5 | **#169 (Fanvue's official connection) is unmerged** and now conflicts with main | open PR |
| 6 | **The open-source watch's "already running" list names only llama.cpp** (also running: ComfyUI, SearXNG), so they could show as "new" | `src/bau/data/scout_watch.yaml` |
| 7 | **yt-dlp is not installed by BAU**, so "watch a video" depends on the owner installing it once | `src/bau/watch.py` |
| 8 | **`bau selftest` fails in a fresh home** without podman, AppArmor tools, chrony or the audit key. On the stick they exist; elsewhere the message names each | `bau selftest` here |
| 9 | **Unused code**: `APIConnector` in `src/bau/platforms.py` is never used and only raises | grep |
| 10 | **About 290 old branches** on GitHub, most from merged work | `git branch -r` |

## P3

- Anchor the audit chain off the machine: the command `bau audit anchor` exists but has never
  been run (the checklist says not started).
- Project Genesis (import the historical AI corpus): not started.
- Accessibility (keyboard-only and screen reader): partial.
- Instagram adapter: planned.
- OpenCode: not part of BAU. Only a research note mentions it; nothing installs or uses it.

## The shortest safe path to a working product

1. **Desktop, today (owner):** the three commands under P0, then `bau money` and paste the output.
2. **Fanvue (owner, about 10 minutes):** register the redirect address, then `bau fanvue login`. This
   is the one link that blocks every dollar.
3. **Code (P1-3):** make the job record and the world tell the truth about unverified work.
   It is small and contained.
4. **Code (P1-2):** an agent for the first sellable mission type, chosen in Prompt 5.
5. **Owner and counsel (P1-4):** work through the RED list. It decides what may be claimed to
   customers; it does not stop internal use.
