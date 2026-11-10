# AUTOMATON AI: security review (2026-11-10)

Controls as they are in the code and on the desktop, then the open findings. "Live" means
seen on the desktop on 2026-11-10.

## Controls in place

| Control | Where | Proof |
|---|---|---|
| One path from an agent to a capability, 8 checks in order | `src/bau/gateway.py` | tests; live: 4 refusals on an untrusted network |
| Human-only approvals; consequential actions staged for the owner's click | `assistant._run_tool` (`confirm` tools), `bau approve`, SSH-signed mission approval | tests; live: 17 confirms, 24 declines |
| Governor HOLD: only read-only actions run | `src/bau/governor.py`, gateway step 2b | tests; live: 1139 ticks |
| Tamper-evident audit | hash-linked chain, `bau audit` verifies | live: 1721 events |
| Untrusted data stays data; a turn that read outside content may only read | `agents.untrusted`, the gateway's taint rule | tests |
| Network trust per network | `src/bau/network.py`; trusting a network is refused to non-humans | live: refused when Claude tried it |
| Data boundary per hosted provider; local-only switch; $0 automaton uses local models only | `models/router.provider_allows`, `localonly.py`, `pick_model` | tests |
| Secrets in `/etc/bau/*.env` (root:bau 0640), secret scan in CI | `bau secrets`, `scripts/check.sh` | CI |
| Hands: one command at a time, owner's `y`, sudo refused | `src/bau/hands.py` | tests |
| Adults only, AI label, owner's limits on every post | `virtual_creator.MINOR_REFERENCE`, the Fanvue queue checks | tests |

## Findings

| # | Finding | Severity | State |
|---|---|---|---|
| 1 | The local voice service on 127.0.0.1:8767 has no login; a program squatting the port could feed Jarvis words | medium | mitigated: replies must be WAV or a short transcript (#155). Open: a shared secret, with its installer on `main` |
| 2 | The automaton posts without the owner's per-post Accept | by the owner's choice (2026-11-10) | every content check still runs; $0 budget; it dies (HOLD) after 30 days without income |
| 3 | The installed BAU lags `main` | medium | owner step: `sudo bau update now` |
| 4 | Memory has no retention policy | low | open (roadmap, memory layer) |
| 5 | Jarvis's claims are not checked against tool results ("the assets are ready in your workspace" after a tool that returns prompts) | medium | open (roadmap gap 2) |
| 6 | The real-model check is not in CI, so a model regression can reach the owner unseen | medium | open (roadmap gap 2) |

No change in this review weakens the host: no ports opened, nothing bound beyond localhost.
