# AUTOMATON AI: current state (2026-11-10)

The baseline before any AUTOMATON AI work. Everything here was run or read on 2026-11-10;
nothing is taken from older documents on trust.

## Four levels of capability

A feature only counts at the level its evidence reaches.

| Level | Meaning | Evidence required |
|---|---|---|
| **L0 Proposed** | written in a doc, prompt or plan | none |
| **L1 Implemented** | code exists and is reachable | file and function |
| **L2 Tested** | an automated test proves the behaviour (with fakes) | a named test |
| **L3 Proven live** | ran on the owner's desktop or with real data | a command run, log or audit row |

The A-E classes in `CAPABILITY_MATRIX.md` say how complete a capability is; the L level says
how far it is proven. "Implemented and tested" (A) can still be L2 only.

## Baseline

| What | Result |
|---|---|
| Code | `main` at `54fab28` (github.com/BSAJabo258/linux-ai-biz) |
| `bash scripts/check.sh` | ALL PASS: lint, secrets, regulations, shellcheck (42 scripts), 1053 tests passed, 20 skipped |
| CI | the same script on Python 3.11 and 3.13, green on every merge |
| Real-model check (`.claude/skills/real-model-check/run.py qwen3.5-9b`), the live model on the desktop | **7/8** before the first improvement; **8/8 twice** after it |

## The machine (the owner's desktop)

| Fact | How it was seen |
|---|---|
| Local model `qwen3.5-9b` answers on 127.0.0.1:8080 | `GET /v1/models` |
| Pictures: ComfyUI on the RTX 3060 (11.7 GB), 0 restarts since `libcuda1` was installed | `/system_stats`, `systemctl show bau-pictures` |
| Chroma (levels 2-3) installed, three files checked by SHA-256 | the owner's setup window |
| Voice: `bau-voice` (Kokoro + Whisper) on 127.0.0.1:8767 | `/health`, a sentence spoken and heard back word for word |
| Network trusted (the owner's hotspot) | `bau network status` |
| Installed BAU is older than `main`: the automaton, local voice and God's Eye changes are not on the machine until `sudo bau update now` | `/opt/bau/venv/.../bau/automaton.py` absent |
| Fanvue not connected; no revenue rows | no `fanvue/` folder in `/var/lib/bau`, no `economics/revenue.jsonl` |

## What has actually run (the audit chain, 1721 events)

| Events | Count |
|---|---|
| governor ticks (the watchdog) | 1139 |
| Jarvis tool calls outside the gateway (older versions) / through the gateway | 233 / 57 |
| gateway refusals (untrusted network) | 4 |
| owner confirmed / declined a staged card | 17 / 24 |
| models benchmarked | 11 |
| autopilot tasks queued / done | 9 / 9 |
| missions planned / run | **2 / 0** |
| agent runs (`ask_agent`) | **0** |
| pictures drawn, posts made, money earned | **0 / 0 / $0** |

Live tool use by Jarvis: `use_tool` 76, `system_status` 29, `web_search` 23, `tool_menu` 18,
`toolbox` 12, `brain_lookup` 11, `recall` 11, `missions` 8, `plan_mission` 2, `remember` 1.

## One naming correction

In the code, **God's Eye is world data** (`src/bau/spatial.py`: earthquakes, aircraft,
satellites, cameras, the sky). The governance the AUTOMATON AI prompt calls "God's Eye"
(inspect actions, enforce permissions, audit, stop unsafe work) is the **Universal Gateway**
(`src/bau/gateway.py`), the **Governor** (`src/bau/governor.py`) and the **audit chain**
(`src/bau/audit.py`). This audit measures governance where it is, and God's Eye for what it
does.
