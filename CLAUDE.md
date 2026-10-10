# CLAUDE.md - BAU/BSA

BAU is a compliance-first AI business system for one owner: an encrypted Debian laptop
built from two USB sticks, a Python control plane (`src/bau`), and work layers on top
(Jarvis, agents, factories, publishing). Read `docs/HANDOFF.md` first for where things
stand and what is next.

## Layout

| Path | What |
|---|---|
| `src/bau/` | the package. `cli.py` + `cli_ext.py` = the `bau` command; `policy.py`/`regulations.py` = rule engine; `data/` = regulations, policies, factories, registry defaults |
| `src/bau/assistant.py`, `ui/jarvis_server.py`, `ui/jarvis.html` | Jarvis: briefing, conversation, tools, voice HUD |
| `src/bau/publishing.py` | publishing hub; platforms are adapters (`tiktok.py`, `youtube.py`); `kids.py` = made-for-kids rules |
| `src/bau/workspace.py`, `data/workspaces/` | ICM workspaces (`bau ws`): numbered stage folders one agent walks, owner checks each stage; kids-channel pilot |
| `src/bau/scout/`, `data/scout.yaml` | Repo Scout (`bau scout`): finds open-source projects for a capability, keeps claims apart from inspected and tested facts, licence/security gates; never installs or runs them. See `docs/engineering/repo-intelligence.md` |
| `src/bau/studio.py`, `src/bau/media/higgsfield.py` | Video studio (`bau video`): paid Higgsfield clips under the owner's budget; priced first, owner-confirmed, downloaded with provenance, cost in the ledger. See `docs/STUDIO.md` |
| `src/bau/usage.py` | Usage meter (`bau usage`): every model call's tokens and dollars per model (free ones too), owner-set daily limits, busy replies, rate-limit headers, GitHub's wait. See `docs/USAGE.md` |
| `src/bau/governor.py` | watchdog (hold / quarantine / resume, never approves) |
| `src/bau/brain.py` | Second Brain (Markdown vault, nouns + verbs graph) |
| `src/bau/chats.py` | chat library (`bau chats`): the owner's Claude/ChatGPT exports in SQLite FTS5; Jarvis reads them per `bau chats sharing` |
| `src/bau/models/` | providers (Claude, llama.cpp, hosted OpenAI-compatible e.g. Z.ai), router, `bench.py`, `fetch.py` |
| `installer/` | USB #1 image builder, USB #2 payload (`make-payload.sh`), `payload/install.sh` |
| `image/`, `src/bau/live.py` | My Jarvis live USB: `build-live.sh` (Debian Live + BAU + llama.cpp), `live-build/` config, `jarvis-storage` (encrypted persistence); see `docs/MY-JARVIS.md` |
| `Dockerfile`, `docker-compose.yml`, `docker/` | test drive in containers |
| `vm/` | VirtualBox rehearsal scripts (`create-vm.ps1`, `create-vm.sh`) |
| `docs/` | `INSTALL.md` (owner guide), `LIVE-USB.md`, `CLOUD-TEST.md` (free Codespaces + Z.ai), `WORKSPACES.md`, `MY-JARVIS.md` (spec + build order), `ARCHITECTURE.md`, `HANDOFF.md` |
| `tests/` | pytest suite |

## Commands

```bash
python3 -m pip install -e '.[dev]'        # once
python3 -m pytest -q                      # all tests (~30 s)
ruff check .                              # lint (line length 100)
bau reg validate                          # regulations + policies cross-check
bau secrets .                             # secret scan (CI runs it)
shellcheck -x installer/*.sh installer/lib/*.sh installer/payload/*.sh installer/firstboot/*.sh docker/*.sh vm/*.sh image/*.sh
bash installer/make-payload.sh --skip-tests --out /tmp/pl   # build USB #2
bash image/build-live.sh --out /tmp/live                    # live USB image (Docker, ~15 GB disk)
docker compose up -d --build                                # test drive: http://localhost:8765
```

Run tests, ruff, `bau reg validate` and shellcheck before every commit. CI
(`.github/workflows/ci.yml`, `docker.yml`) runs the same on Python 3.11 and 3.13.

## Rules that must not be broken

These are the product's safety model, not style preferences:

- **Approvals are human-only.** Money, commercial email, legal and other signed approvals
  are SSH-signed by a human (`bau approve`). No agent, model, Jarvis or the Governor may
  approve, and none of them may be given a tool that does.
- **Consequential actions are confirmed by the owner.** Posting to any platform, releasing a
  HOLD, and similar actions are only *staged* by Jarvis; they run on the owner's click or
  `y`. Owner-only choices (privacy, audience, made-for-kids, commercial disclosure) never
  come from a model and never have defaults.
- **Never weaken the host.** Don't open firewall ports, disable AppArmor or encryption,
  or bind servers beyond localhost (containers bind their interface only with
  `BAU_IN_CONTAINER=1`; ports are published on 127.0.0.1).
- **Untrusted data stays data.** Tool results go to models wrapped by `agents.untrusted()`;
  Jarvis never reads `<untrusted_data>` blocks aloud.
- **Kids content** goes only to platforms with `allows_kids` (YouTube, made for kids). Never
  route child-directed videos to TikTok or other 13+ platforms.
- **Local models need a real benchmark** (`bau models bench`) before approval; never fake
  availability. Abliterated models stay in the content lane (no tools, local only).
- **No compliance claims.** BAU reports requirements, controls and evidence; it never says
  "compliant", "guaranteed" or "risk-free". Every regulation record awaits counsel review.
- **Platform facts are verified.** When adding a platform or API, check the official docs,
  record facts with the date in the module docstring and an `examples/platform-*.yaml`
  policy record, and cite regulations by `reg_id` in `data/policies/`.

## Conventions

- Match the surrounding code: stdlib first, small functions, comments only where the
  reason is not obvious. New policy rules go in `src/bau/data/policies/*.yaml` and must
  reference existing `reg_id`s (the loader refuses dangling references).
- Every behaviour change gets a test. Tests use fakes (`ScriptedProvider`, `FakeTikTok`,
  `FakeYouTube`), never real network or keys.
- The owner prefers **few commits**: one finished commit per feature on a branch, a
  draft PR, squash-merge when CI is green. Don't push half-finished work.
- Docs are written for a non-technical owner: plain words, exact commands.
- Secrets never go in the repo: keys live in `/etc/bau/*.env` on the laptop or `.env`
  (gitignored) in the test drive.
