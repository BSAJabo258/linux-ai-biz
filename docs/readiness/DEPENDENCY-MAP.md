# Dependency map (2026-11-18)

What each part of BAU needs to work, where it runs, and whether that need is met. "Met here"
is this audit's cloud machine; "desktop" is the owner's headquarters as last seen.

## The request path, as traced

One owner question, as it ran on 2026-11-18. Each step names the code and how it was proven:

```
owner types in the page          src/bau/ui/jarvis.html            ran (Playwright, 0 page errors)
  → POST /api/ask (key checked)  src/bau/ui/jarvis_server.py       ran (202, then the answer)
  → Jarvis picks a model         assistant.pick_model              ran (qwen3.5-4b, local)
  → facts first / tool choice    assistant.GROUND, Assistant.tools ran (missions tool)
  → every tool through the gate  src/bau/gateway.py                ran (audit rows)
  → tool reads the store         jobs/missions.jsonl               ran
  → answer + cards to the page   /api/job/<id>                     ran (200, right answer)
```

A mission, as it ran:

```
plan (type, policy gates)        jarvis.Jarvis.plan                ran → READY
  → agent for the type           jarvis.AGENT_FOR                  only "research" has one
  → readiness (6 checks)         agentfolders.readiness            ran → all ok
  → executive job                executive.py + jobs.JobStore      ran (job record wrong, see issues)
  → agent loop, tools via gate   agentfolders.run → agents.run     ran (search.web, read page)
  → verify facts vs tool results jarvis.agent_executor             ran → caught 1 unbacked phrase
  → PAUSED for the owner         mission store, governor finding   ran
  → world / portfolio / Jarvis   world.py, jarvis.portfolio        ran (world showed it wrong)
```

## Services on the desktop (all on 127.0.0.1 only)

| Service | Port | Needed by | Set up by | Met here | Desktop |
|---|---|---|---|---|---|
| Local model (llama.cpp b11747) | 8080 | Jarvis, agents, captions | the stick / `bau pack install` | yes (built at the pinned commit) | yes (`qwen3.5-9b`, owner) |
| Jarvis | 8766 | the owner, the laptop's tunnel | `sudo bau hq on` | yes (in-process) | yes, after the port fix |
| Web search (SearXNG) | 8888 | researcher, `web_search` | `installer/bau-search-setup.sh` | yes (pinned commit) | not known |
| Pictures (ComfyUI) | 8188 | creator feed, portraits | `installer/bau-pictures-setup.sh` | no (no graphics card) | yes (11-10) |
| Voice (Kokoro + Whisper) | 8767 | spoken replies, the mic, video without captions | **nothing in the repository** | no | yes (set up by hand) |
| SSH (keys only, home network) | 22 | the laptop station | `sudo bau hq on` | n/a | yes (owner 11-17) |

## Outside accounts and keys (names only, never values)

| Need | Used for | State |
|---|---|---|
| Fanvue app (client id and secret) + sign-in | posting, earnings | keys: not known; sign-in: **not connected** |
| Fanvue redirect `http://127.0.0.1:3456/callback` registered | the sign-in | **owner to do** |
| TikTok app keys / Ayrshare | TikTok, a week of posts | not set |
| Hosted model keys (Claude, Z.ai and others) | the strong brain, faster answers | optional; local works without them |
| ElevenLabs | cloud voice | optional |
| Higgsfield | paid video | optional, needs a budget |
| GitHub (no token needed) | Repo Scout, the watch, updates | works without a token (rate limited) |

## Packages and pinned projects

| What | Pinned | Checked by |
|---|---|---|
| Debian packages for the stick | `image/live-build/config/package-lists/my-jarvis.list.chroot` (87) | the installer's list is fully inside it (checked 2026-11-18); the stick build in CI |
| llama.cpp | b11747, commit `f711c8f3` | `image/inside.sh` refuses any other commit |
| ComfyUI | commit `17ff1dcc` | `installer/bau-pictures-setup.sh` |
| SearXNG | commit `81371861` | `installer/bau-search-setup.sh` |
| Models | SHA-256 in `src/bau/data/registry_defaults.yaml` | `bau models fetch`, `bau pack install` |
| BAU itself | the `bau-update` release (wheel + SHA-256) | `src/bau/update.py`; release = main `dba8907` on 11-18 |

## Machines

| | Desktop (headquarters) | Laptop (station) | This audit |
|---|---|---|---|
| Hardware | RTX 3060 12 GB (owner) | Dell XPS 13 9380, 8 GB, no NVIDIA | 4 cores, 15 GB, no graphics card |
| System | Debian 13 from the 128 GB stick | to be installed on the 1 TB WD from release `live-v0.1.0-9ae6e0f` | Linux container, Python 3.13.18, Node 22.23.4 |
| BAU | `9ae6e0f` (owner, 11-17); update pending | not installed | main `1d82c70` |
| Network | USB tether to the tablet | tablet hotspot, or a cable (not proven) | cloud, through a proxy |
| Coding agents | not known | not known | Claude Code; OpenCode not installed |

Facts about the owner's machines come from the owner's pasted output and `docs/automaton/CURRENT_STATE.md`.
This audit could not reach either machine: no computer was connected to the session. The
commands to fill in the missing facts are in [PROJECT-STATUS.md](PROJECT-STATUS.md).
