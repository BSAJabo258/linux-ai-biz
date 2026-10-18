# Handoff: BAU/BSA - state on 2026-10-07

For Claude Code in VS Code on the owner's computer, picking up from the cloud session that
built BAU. Read `CLAUDE.md` for layout, commands and the rules that must not be broken.

## What exists (all merged to `main`)

| PR | What |
|---|---|
| #1-#4 | USB installer (two sticks), control plane, compliance engine, Governor, TikTok review-and-post, Second Brain, GitHub Actions USB build (`build-usb.yml`) + Codespaces |
| #5 | Jarvis: spoken briefing, conversation with memory, tools, owner-confirmed actions, voice HUD (`bau jarvis`) |
| #6 | Publishing hub (`publishing.py`) with TikTok + YouTube adapters; made-for-kids rules (`kids.py`, `policies/kids_content.yaml`); `kids_channel` factory |
| #7 | Docker test drive, VirtualBox rehearsal scripts (`vm/`), GLM-4.7-Flash free local fallback, `bau models bench` |
| #8-#11 | This handoff; VM scripts size memory from the host, fix an existing VM, stop with BIOS steps when virtualisation is off; VS Code task |
| next | **My Jarvis OS, MVP #1**: live USB (`image/`, `docs/LIVE-USB.md`), encrypted persistence (`jarvis-storage`), Qwen2.5-1.5B local model (`bau models fetch`), spec mapping and build order (`docs/MY-JARVIS.md`) |

State: 558 tests pass (one skips when run as root); 49 regulations / 65 policies validate.

The BAU Pack (2026-10-18, `docs/PACK.md`): BAU is installed on the owner's laptop (boots
from the SanDisk via F12, Jarvis and Mission Control work offline) but it has no AI model
and no Wi-Fi yet (Killer 1435 / QCA6174, ath10k). `BAU-Pack-Make.cmd` fills a stick on
Windows with the three pinned models and `BAU-KEYS.enc`; `sudo bau pack install` on the
laptop copies, starts, benchmarks and (on yes) approves the boss, and writes a redacted
`laptop-report.txt` to the stick.

No Wi-Fi, found 2026-10-18: `auto/config` builds with `--apt-recommends false`, and
network-manager only *recommends* `wpasupplicant`, so the image had no Wi-Fi login program
at all (the firmware, firmware-atheros, was there). The package list now names
`wpasupplicant`, `wireless-regdb` and `iw`; the pack carries the same seven .debs (pinned
SHA-256, deb.debian.org then snapshot.debian.org) for the laptop already installed, plus
`bau-main.zip` so that laptop gets `bau pack`. Not yet confirmed on the laptop itself.

The owner's direction (2026-10-07): grow BAU into **My Jarvis OS** here, following their
spec (`docs/MY-JARVIS.md`): live USB first, install-to-disk kept, one phase per PR. Next is
Phase 4 is now **ICM workspaces first** (`docs/MY-JARVIS.md`, "structure before frameworks"):
`bau ws` + the kids-channel pilot are built; next, run real episodes with the free model and
convert the next factory. Hermes (4b) only where workspaces can't do the job.

The owner's PC (12 GB, virtualisation off) can't run the full model, so testing runs in the
cloud for free (`docs/CLOUD-TEST.md`): GitHub Codespaces runs BAU, and Z.ai's free hosted
GLM-4.7-Flash (`glm-4.7-flash-zai`, adapter `openai_compat`, key in `ZAI_API_KEY`) is
Jarvis's model. First real bench on 2026-10-07 (owner's PC, WSL): `reply_ok` and
`tool_calls` true, about 3 s per reply, after four "429 overloaded" replies from Z.ai. The
provider now waits and retries busy replies (5, 10, 20, 40 s) and shows the service's own
message. The owner still has to bench and approve it in their codespace.

Repo Scout (`bau scout`, `src/bau/scout/`, docs in `docs/engineering/`) finds and ranks
open-source projects for a capability on evidence; it never installs or runs them, and
licence/security are gates a score cannot override. Baseline audit before it:
`docs/engineering/baseline-audit.md`. Never run against live GitHub search yet (the build
container can't reach it); the owner's first `bau scout find` in the codespace is the test.

The video studio (2026-10-10, the first paid integration, tests written first in
`tests/test_studio.py`):
- `bau video`, `studio.py` and `media/higgsfield.py`;
- Higgsfield's API facts are checked and dated in the module docstring, and its provider
  record is in `registry_defaults.yaml`;
- the money rules: an owner-set budget with no default; the provider approved by the owner;
  each clip priced by Higgsfield's estimate and refused when over the per-clip or monthly
  budget; clips start only on a human Confirm or `y`; HOLD stops new clips; finished clips
  are downloaded through the media gateway (provenance sidecar) and their cost goes in the
  ledger;
- Jarvis has `make_video` (confirm) and `video_clips`, and a Studio node and panel;
- owner guide: `docs/STUDIO.md`.

Never called against the real Higgsfield API yet: the owner's first `bau video quote` is the
first real call.

The repo page, round three (2026-10-10): `hero-*.svg` replaces the banner - a holographic
globe (Natural Earth land rolling behind a shaded clip circle), golden halo rings, ripples,
twinkling stars, an animated title gradient and a typing line cycling four phrases; the
demo GIF now sits right under it (800x450, 48 frames, ~2 MB, starts on the action);
`divider-*.svg` between sections. `assets/make_art.py` is exempt from E501 (SVG templates).

God's Eye panel (2026-10-10, tests first in `tests/test_godseye_panel.py`): node `godseye`,
`screen.godseye_query/layer/screen/world`, `/api/godseye` (lane `godseye`) and
`/api/godseye/world`, Jarvis tool `world_watch`, a map overlay (`#eye`, canvas, radar sweep,
reduced-motion still) over `data/world-land.json` (Natural Earth 110m land, simplified,
public domain). Aircraft by wide named region only and private registrations masked;
5-minute cache; a 429 sets a wait per layer; `godseye.query` audit with purpose. Driven
against the real USGS, OpenSky (got 429, wait honoured) and CelesTrak feeds.

The repo page, round two (2026-10-10, tests in `tests/test_repo_look.py`): a real Jarvis
GIF (`assets/jarvis-demo.gif`, recorded with Playwright, 960x540, 76 frames), an animated
terminal SVG of real commands, a stats panel whose numbers `make_art.facts()` reads from
the repo (a test fails if they go stale: rerun `python3 assets/make_art.py`), GitHub
[!IMPORTANT]/[!TIP] notices. Jarvis answer cards for usage_today, toolbox, plan_episode
and clip_prompt now use readable layouts instead of raw fields.

The kids series engine (2026-10-10, tests first in `tests/test_series.py`): `series.py`
reads `_shared/characters/*.yaml` + `_shared/style.yaml` (templates with placeholders in
the kids-channel workspace); `lock(id)` is the fixed character sentence every prompt
carries; `prompt()` = style + locks + scene + avoid (kids scan, 2500-char cap); `drift()`
flags off-sheet colours/"never" traits and names without their lock (stage 04 check
`series_lock`, active once sheets are filled); `plan()` scales `data/series_formats.yaml`
beats to 3-15 s clips, writes `series.yaml` + `series-plan.md`, warns on four same formats
in a row or a near-duplicate idea. Jarvis tools `clip_prompt`, `plan_episode`; `bau series`.

The repo's look (2026-10-10, tests in `tests/test_repo_look.py`): README opens with an
animated banner and feature cards (`assets/*.svg`, dark and light via `<picture>`, drawn by
`assets/make_art.py`; self-contained, still for reduced motion), badges, a real Jarvis
screenshot, a Mermaid "how it works" diagram and a "where it runs" table. Mission Control
(`ui/page.html`) now uses Jarvis's palette (offline, system fonts, a11y lint clean).

The owner's own cloud server (2026-10-10, tests first in `tests/test_cloud_vm.py`; the
owner chose DigitalOcean, Debian 13, no GPU): `installer/cloud/cloud-init.yaml` +
`prepare.sh` (admin login from the droplet's key, sshd keys only, payload built in the
admin's home; a temporary NOPASSWD sudoers file that `install.sh --cloud` removes after
the owner sets a password), `install.sh --cloud` (`nftables-cloud.conf` = laptop rules +
rate-limited SSH, sticky via `/etc/bau/cloud`; `bau-jarvis.service` as the owner on
127.0.0.1 with a fixed key from `bau jarvis url`; audit `install.cloud`). Rehearsed end to
end in a systemd Debian 13 container: prepare, install over SSH with typed answers, new
SSH login after the firewall, root and passwords refused, Jarvis 200 through the tunnel,
403 with a wrong key, unreachable directly, key not in the journal, SSH kept on a plain
re-run. Not yet run on a real droplet. Owner guide: `docs/CLOUD-VM.md`.

The toolbox (2026-10-10, tests first in `tests/test_toolbox.py`): `data/toolbox.yaml` has
77 open-source tools researched that day (connectors/MCP, Claude Code setup, grounding,
structured output, guardrails, evals, agents incl. Hermes Agent and Hermes 4, memory, local
models, voice, video), each with sources, licence and caveats; validated by `bau toolbox
validate`. `Toolbox.ask` answers plain-words questions; Jarvis's `toolbox` tool and system
prompt make him look there before guessing; the Scout panel shows "Already known" first.
`bau toolbox check NAME` -> `Scout.add` (one GitHub record) + `Scout.inspect`. Rebuilt from
research because the owner's own transcript collection was lost with a codespace.

The full stick (2026-10-12, tests first in `tests/test_full_stick.py`): the owner chose
"both" on one 128 GB stick. `image/live-build/auto/config` now has `--debian-installer
live`. The installer copies the live squashfs (live-installer) and its answers are in
`config/includes.installer/preseed.cfg`, repacked into its initrd:
- partitioning, accounts, clock and grub match `installer/preseed/bau.preseed`, and a
  test keeps them identical;
- the disk, confirmations, passphrase, password and time zone are never preseeded;
- no tasksel desktop is installed and pkgsel upgrade is none.

The grub menu has "Install BAU on this laptop" (@KERNEL_GI@); syslinux keeps live-build's
install entries. `build-live.sh` stages `/BAU-PAYLOAD` (sums verified) and `/bau`
(firstboot-setup.sh, live-to-disk.sh, hardening) on the stick. `late_command`:
- copies the bootstrap;
- runs `live-to-disk.sh /target`, which removes bau-live-init, the live.conf drop-ins,
  the setup autostart and the enable links of BAU's services (install.sh enables them);
- copies and re-checks the payload;
- runs firstboot-setup.sh.

Verified end to end in QEMU (TCG, no KVM) from a real image build (1.3 GB):
- an unattended install (test-only answers on the kernel line) took ~43 min;
- the installed system boots, asks for the LUKS passphrase, and `bauadmin` logs in;
- `/opt/bau-payload` sums OK, the live packages are gone, nftables has policy drop, BAU
  0.3.0 and llama.cpp are present, and the motd points to install.sh.

The first run found bau-recover and bau-ui failing before install.sh; that was fixed and
re-verified. Not yet done on real hardware, and `install.sh` was not run in the VM
(no network there).

The laptop check (2026-10-12, tests first in `tests/test_laptop_check.py`) answers "can
BAU go on this laptop?" before anything is changed. Both scripts are read only and ship in
the payload (so on the stick in `/BAU-PAYLOAD`); see `docs/LAPTOP-CHECK.md`.
- `installer/bau-laptop-check.ps1` runs on Windows without Python. `Get-BauSummary` turns
  the inventory into a verdict with blockers, warnings and notes. Blockers are under 8 GB
  of memory, a 32-bit system, or no internal disk of 64 GB. Warnings are BitLocker (with the
  recovery-key step), legacy BIOS and Broadcom Wi-Fi.
- Each device is judged by its PCI vendor. The tests run that logic under pwsh on Linux.
- The summary carries no host, user, MAC, IP or serial. Those stay in the private JSON.
- `installer/bau-laptop-check.sh` runs from the stick and shows `lspci -nnk` drivers
  (`NO DRIVER LOADED`), missing-firmware kernel lines and rfkill. MACs and IPs are
  scrubbed from its summary.

Finishing the install by itself (2026-10-12, tests first in `tests/test_finish_install.py`):
on a laptop installed from the full stick, `firstboot-setup.sh` writes an XDG autostart
(`/etc/xdg/autostart/bau-finish-install.desktop`) that opens `finish-install.sh` in a
terminal at login. It waits for the internet (install.sh adds podman, auditd, ffmpeg...),
then runs `sudo bash /opt/bau-payload/install.sh`; the owner types the sudo password and
the approval-key passphrase, the script never sees them. install.sh removes the autostart,
so it comes back at each login until BAU is installed. The installer itself still asks
only the owner's four answers (disk + confirm, passphrase, password, time zone).

Keys transfer (2026-10-13, tests first in `tests/test_keys_transfer.py`): the owner's API
keys come from their other computer in one locked file. `bau-keys-export.ps1` (Windows,
double-click `BAU-Keys-Export.cmd`, drop .env files on it) and `bau-keys-export.sh`
(Mac/Linux, bash 3.2-safe) collect credential-shaped names from the environment and .env
files, show names only, and write `BAU-KEYS.enc` in openssl's `enc -aes-256-cbc -pbkdf2
-iter 600000 -md sha256` format (the PS1 does it in .NET; a test opens its output with
openssl). `sudo bau keys import` (`keys.py`) routes platform app keys to platforms.env and
the rest to models.env (0640, root:bau), replacing same names and keeping other lines, and
audits names only. openssl is now in the live image and install.sh's packages.

Offline stick (2026-10-13, tests in `tests/test_full_stick.py`, `test_finish_install.py`):
every package install.sh needs (podman, uidmap, auditd, unattended-upgrades, bind9-dnsutils,
ffmpeg, openssl) is in the live image, so `finish-install.sh` runs `install.sh --offline`
first and only waits for the internet if that fails (an older stick). Found when the
owner's XPS 13 had no Wi-Fi after installing. LIVE-USB.md explains phone USB tethering.

Open-source watch (2026-10-13, tests first in `tests/test_scout_watch.py`): the owner's
"Repo Intelligence & Optimization Engine". Repo Scout already did discovery, claims vs
evidence, licence/security gates and quarantine inspection; this adds the standing watch.
`scout/watch.py` runs `data/scout_watch.yaml` (9 categories incl. observability, 2 searches each, seeds,
`integrated`, owner priority 1-3) weekly via `bau-scout-watch.timer` (as bau, optional
GITHUB_TOKEN), tags candidates with categories and dated star/push snapshots (`KEEP` keeps
them across runs), and `shortlist` ranks new projects (test next / watch) apart from what
BAU runs or the Toolbox researched, and from licence-blocked ones (ignore). Cost stays
"unknown until benchmarked"; nothing is ever "adopt". Next: benchmarks of shortlisted
tools in the sandbox (model lab: `bau models bench` exists for models).

Agents as folders (2026-10-12, tests first in `tests/test_agent_folders.py`): the
owner's point was that agents are folders (instructions + skills + tools/MCP + a brain),
not models. `agentfolders.py` loads `BAU_HOME/agents/NAME/` or shipped `data/agents/NAME/`
(the owner's wins):
- `AGENT.md` frontmatter: name, description, brain, tools, mcp, skills, max_steps; the
  body is the instructions;
- `skills/*/SKILL.md` follows the Agent Skills spec, checked 2026-10-12 at
  agentskills.io/specification: name up to 64 characters `[a-z0-9-]` matching the
  folder, description up to 1024 characters;
- shared skills live in `BAU_HOME/skills/`.

`purpose()` lists only skill names and descriptions; the gateway tool `inspect.skill`
opens one, and its text comes back wrapped as untrusted. `approve()` is human only and
stores the folder's sha256 in `config/agent_approvals.yaml`; any change makes it
"changed since approval" and `run()` refuses. `run()`:
- resolves the brain via `brains.resolve`;
- builds the gateway with `agent_tools[folder:NAME]` = AGENT.md tools + `inspect.skill`;
- attaches approved MCP servers from `mcp:`;
- has no tools for a content brain.

`add_skill()` copies only .md/.txt files and lists the scripts it skipped. `new()` copies
a starter agent. Shipped agents: `researcher` (strong; cite-sources, ask-before-guessing)
and `producer` (small; plain-words, draft-for-review). `bau agents
list|show|approve|run|new|add-skill`; Jarvis has `agents` (read) and `ask_agent` (act).
The toolbox gained 9 more tools (100): Agent Skills standard, Awesome Agent Skills, skills
CLI, Claude Agent SDK, Google ADK, Microsoft Agent Framework, Kestra, Windmill (AGPL) and
Temporal SDK. The capability map's agents and workflows layers name them.

Brains per stage (2026-10-12, tests first in `tests/test_brains.py`): the owner's idea
was to let the files-and-folders workspaces replace a pile of agents and models. A stage's
`CONTEXT.md` `## Brain` names its brain:
- `small`: a free local model;
- `strong`: Jarvis's model or the owner's choice, and the default;
- `content KIND`: the content-lane model, only for a KIND in its `use_for`.

`brains.py` handles `config`/`choose`/`resolve`:
- only a person chooses (`bau ws brains`); this is audited as `brains.chosen`;
- small falls back to strong and says so;
- content is never defaulted, is refused in a workspace that `for_kids()`, and a content
  model can't be small or strong (nor the reverse).

Jarvis's `draft_stage`:
- uses the stage's brain, metered under that model;
- takes `brain=small|strong` to redo an unchecked draft (`W.awaiting_check`).

`bau ws run --brain`. The kids template uses small for pitch/storyboard/metadata and
strong for script/video prompts. The registry gained `qwen3.5-4b`, `qwen3.5-0.8b` and
`qwen3-4b-heretic-content` (content lane, port 8082). Their pinned downloads and sizes
were checked 2026-10-12 from the HF API, GGUFs are by unsloth/mradermacher, and all are
REGISTERED, so the owner benches and approves them. Not yet run on real hardware; whether
the live image's llama.cpp supports qwen35 is unverified (the bench will say).

The capability map (2026-10-12, tests first in `tests/test_capability_map.py`):
`data/capability_map.yaml` lists 13 layers. Each layer has a status (have/partial/gap),
the BAU files that already do the job, and toolbox tools with a plan
(direct/adapter/later/skip, plus why). It also carries rules, a next step and a build
order: 1 web (four permissions read/fill/draft/submit; submit is the owner's), 2 connect,
3 computer use, 4 workflows, 5 documents, 6 verification, 7 agents, 8 coding.
`CapabilityMap` lives in `toolbox.py`: `problems()` checks the BAU paths, that every tool
is in the toolbox, the plans, and that there are no claims. `bau toolbox map [--layer]`,
the `capability_map` tool, and `bau toolbox validate` check the map too. The toolbox gained
14 tools (browser, computer-use, documents categories, and AgencyBench), each with its own
`checked: 2026-10-12`. Licence flags are recorded:
- Skyvern and workflow-use are AGPL;
- Marker's weights need a paid licence above $5M;
- OmniParser's licence file and README disagree;
- Cua has mixed licences;
- Browserable has had no commits for about 14 months.

Owner decisions (2026-10-12):
- USB is both: the same 128 GB stick runs Jarvis live and installs BAU on the laptop.
  The installer is already one stick (#50, `bau-one-debian-*.iso`). The plan to combine
  it with the live image is lb_config `--debian-installer live` in the live image, so one
  direct-written image keeps the encrypted storage. Ventoy persistence uses a backend file; Debian and
  LUKS are not on its tested list (unverified).
- Compute is hybrid.

Next build: the browser lane (map layer 1), then the one-stick installer.

The results tracker (2026-10-10, tests first in `tests/test_results.py`): `results.py`
reads numbers back for every POSTED queue item, read only. YouTube uses Analytics
`reports.query`, `dimensions=video`, batches of 200, with `estimatedRevenue` asked
separately; a refusal means "no earnings" and views still count. TikTok uses
`/v2/video/query/`, 20 per request. Both clients gained the read scopes, so owners log in
once more. Other behaviour:
- snapshots go to `results/snapshots.jsonl`, one refresh per platform an hour;
- `bau results link` ties a video to its studio clips and episode; cost comes from the
  ledger's `job_id`, and the format from the episode's `series.yaml`;
- the report shows profit per video, unlinked clip spend, `by_format` and `what_works`;
- it is reachable through the `results` tool, a Results node and panel, `/api/results`
  and `/api/results/refresh`.
Owner guide: `docs/RESULTS.md`.

The usage meter (2026-10-10, tests first in `tests/test_usage.py`):
- `usage.py`: `Metered` wraps the provider for Jarvis's turns, workspace drafts and Scout;
  each call goes to `usage/calls.jsonl` (which model answered, tokens, price, ms, errors);
  paid calls go to the ledger once (moved here from `Assistant._turn`);
- `FallbackProvider.last_failed` records busy backups; `x-ratelimit-*` headers are kept
  as sent;
- owner-only daily limits (`bau usage limits`, `config/usage.yaml`): Jarvis stops calling
  the model and says so;
- `bau usage`, the `usage_today` tool, a Usage node and panel, `/api/usage`; GitHub's
  wait from `scout/github-rate.json` shows there too. Owner guide: `docs/USAGE.md`.

The full Jarvis screen (2026-10-09):
- live work per node: `activity.py`, `/api/activity`;
- working panels: Scout search/inspect/report, model Test, draft editing (`ui/screen.py`);
- timeline from the audit chain (`/api/timeline`);
- Mission Control views inside (`/api/mc/<view>`);
- phone ring with pinch and swipe;
- opt-in wake word and alerts;
- light theme, zoom, a key for every button.

Tests were written first: `tests/test_jarvis_live.py`. The page passes `bau a11y lint`.

The look (2026-10-09, `tests/test_jarvis_look.py` written first):
- a rotating 720-point particle orb in a golden halo;
- energy streams across the screen, and circuit traces from the screen edges to every
  node, with pulses that speed up while that node works;
- a voice bar with a waveform, a "Speaking - tap to stop" pill, and a Chat/Voice pill;
- calmer motion for reduced-motion users.

A test runs `node --check` on the page script, because a text check missed a syntax error
once. It runs at 60 fps at 1600x900 and on a phone-sized screen in headless Chromium.

The Jarvis screen (`ui/jarvis.html`, data from `overview.py` via `/api/overview`) shows the
business as live nodes around the core (team, systems, connections). Producer walks
episodes with buttons: Draft (`/api/draft`, the same act Jarvis may do) and Read & check
(`/api/check` stages an owner-only `check_stage` card in `Assistant.owner_tools`, never
offered to a model; Confirm runs it). Model approval stays a typed command.

**Chat library** (`chats.py`, `bau chats`, `docs/CHATS.md`): the owner's Claude and ChatGPT
export ZIPs go into `BAU_HOME/chats/chats.db` (SQLite FTS5). Jarvis gets the read tools
`chat_search` and `chat_read`. On any model not marked `deployment: local` they work only
after the owner types `bau chats sharing cloud`; there's no default. Neither export layout
is documented by its vendor; the parser is tolerant and reports skipped items. Not yet run
on the owner's real exports.

The owner's **BAUBSA Operating Constitution** (`data/constitution/*.md`, six layers in the
owner's words; `docs/CONSTITUTION.md`) goes into Jarvis's system prompt on every turn,
after PERSONA's safety rules and below them. `bau init` copies it to
`BAU_HOME/constitution` once; owner edits are kept and read live. Jarvis's `recall` tool
reads back what `remember` saved (memory used to be write-only for him).

## What was verified, and how

- **My Jarvis live USB (MVP #1), 2026-10-07:** `my-jarvis-0.1.0-amd64.iso` (910 MB) was
  written to a 16 GB raw disk attached to QEMU as a USB stick.
  - UEFI (OVMF) boot shows the My Jarvis GRUB menu.
  - First boot came up in LIMITED mode, with nothing private created.
  - `jarvis-storage setup` added a 15.1 GB LUKS2 `persistence` partition after the system.
  - Restart: live-boot asked "Please unlock disk", then PRIVATE mode. `/etc/bau` and
    `/var/lib/bau` came from the encrypted container, keys were made on the machine,
    and Mission Control returned 200.
  - `bau models fetch` verified the SHA-256.
  - The image's llama.cpp served Qwen2.5-1.5B inside the VM, and `bau models bench`
    gave reply_ok and tool_calls. It was then approved.
  - Jarvis was told a fact. After a restart and unlock, asked for it, he answered
    correctly ("Teal").
  - Caveat: the cloud VM has no KVM, so its CPU is emulated at about 0.4 token/s. The
    two Jarvis conversations therefore used the same llama.cpp build and model on the
    host (`BAU_LLM_ENDPOINT`). On a real 8 GB PC the model runs in the image itself.
  - Not yet tried on physical hardware or a real USB stick.

- **Real install:** USB #1 + USB #2 in a QEMU/OVMF VM (cloud). That covered:
  - UEFI boot, LUKS unlock, `install.sh` exit 0, services up;
  - nftables default-deny, `selftest` passing;
  - a Jarvis talk-through, with the audit chain recording the owner's confirmations.
- **Docker:** built and run, including:
  - Mission Control 200, foreign Host refused (421);
  - Jarvis guards (403 without the key or from a foreign origin);
  - the Governor running.
  - Local model chain: llama.cpp server → `bau models bench` → approval → Jarvis in model mode. This used a 0.6B stand-in model, not the 18 GB GLM file.
- **VM scripts:** tested only against a fake `VBoxManage`. `create-vm.ps1` was also parsed and run under real PowerShell. They have never run against real VirtualBox.
- **GNOME desktop in the cloud VM:** it crashes (SIGSEGV) because the cloud VM is CPU-emulated with no GPU. That's an artifact of the cloud environment; on real VirtualBox with KVM/VT-x it should be fine.

## Next steps (in order)

### 1. VM rehearsal on this computer (the owner's current goal)

Files the owner needs in `Downloads`:

| File | Where it comes from |
|---|---|
| `bau-debian-13.7.0-amd64-netinst.iso` | [release usb-v0.3.0-8a90228](https://github.com/BSAJabo258/linux-ai-biz/releases/tag/usb-v0.3.0-8a90228) |
| `BAU-PAYLOAD-0.3.0.iso` | sent by the cloud session (built from `619fa73`), or rebuild with the commands below |
| `SHA256SUMS.txt` | the one covering *both* ISOs: sent by the cloud session, or regenerate it below. Don't use the release's copy: it predates the payload ISO |

To rebuild USB #2 locally on Linux or WSL (needs `xorriso`; on macOS use `shasum -a 256` for `sha256sum`):
```bash
bash installer/make-payload.sh --with-claude --out dist
xorriso -as mkisofs -V BAU-PAYLOAD -J -R -o dist/BAU-PAYLOAD-0.3.0.iso dist/BAU-PAYLOAD
( echo "f83d787fee47ebe13e46dcf898cc3347ab9a106958d2f7f7b5af9e0c0fc870fa  bau-debian-13.7.0-amd64-netinst.iso"
  cd dist && sha256sum BAU-PAYLOAD-0.3.0.iso ) > dist/SHA256SUMS.txt
```
Or run **Actions → build-usb → Run workflow** on GitHub, which publishes all three. The cloud session couldn't trigger it (403); the owner can.

Then:
- `powershell -ExecutionPolicy Bypass -File vm\create-vm.ps1` (Windows), or `bash vm/create-vm.sh`;
- follow `vm/README.md`.

The scripts size the VM from the host: half its RAM (2-8 GB), never more than 60% or leaving
less than 4 GB, and half its cores (at most 4). A fixed 8 GB froze the owner's 12 GB PC.
Run on an existing VM, they resize it instead (asking before powering it off). VS Code task:
*BAU: create or fix the test VM* (`.vscode/tasks.json`).

This is the **first real VirtualBox run**. Watch for these and fix anything that breaks in `vm/create-vm.*`:
- `--firmware efi64`;
- the SATA DVD attachments;
- the boot order;
- USB #2 automounting at `/media/$USER/BAU-PAYLOAD`.

### 2. Docker test drive (quicker alternative, also works on Apple-silicon Macs)
`docker compose up -d --build`, then http://localhost:8765, then `docker compose run --rm --service-ports jarvis`. See `docker/README.md`. The first real GLM run happens here or on the laptop:

```bash
docker compose --profile glm up -d llm
docker compose run --rm ui bau models bench glm-4.7-flash
```

It needs about 24 GB RAM. Check `reply_ok` and `tool_calls` are true before approving.

### 3. Owner setup still to do
- **Claude:** `ANTHROPIC_API_KEY` in `/etc/bau/models.env` (laptop) or `.env` (Docker), then `bau set-status model claude-opus-5-5 APPROVED`.
- **YouTube:** Google Cloud "Desktop app" OAuth client, then `YOUTUBE_CLIENT_ID`/`_SECRET` in `/etc/bau/platforms.env`, then `bau youtube login`. Apply for Google's API audit; until it passes, uploads stay private. See INSTALL Phase 8b.
- **TikTok:** app keys plus TikTok's app audit (INSTALL Phase 8).
- **ElevenLabs:** the owner's account was blocked ("unusual activity", free tier disabled). Voice falls back to the browser's, and nothing in code is needed.

## Known gaps / ideas (not started)

- Instagram, Facebook and Snapchat adapters for the publishing hub. Each needs one adapter class in `publishing.py`, a client module, an `examples/platform-*.yaml`, and tests. Verify each platform's current API and posting rules first (consent screens, AI labels, age limits).
- The `ghcr.io/bsajabo258/bau` image is private by default. Make it public in the package settings if the owner wants `docker pull` to work without logging in.
- `vm/create-vm.*` has never run against real VirtualBox (see step 1).
- The full 18 GB GLM-4.7-Flash has never been benchmarked (see step 2).
- Jarvis camera (the owner asked for it later; USB webcam): a local frame read by a local
  vision model only when the owner asks, on/off shown on screen, video never leaves the
  machine, no face recognition. Meant for things like checking the VR tent is clear.
- The results tracker has never run against the real YouTube Analytics or TikTok APIs.

## First message to paste into Claude Code

> Read CLAUDE.md and docs/HANDOFF.md. Then help me do step 1 of the handoff: check that
> VirtualBox is installed and that the three files are in my Downloads folder, run
> vm\create-vm.ps1 (or create-vm.sh on Mac/Linux), and walk me through the install inside
> the VM. If the script fails against real VirtualBox, fix it, run the repo checks, and
> open one PR with the fix.
