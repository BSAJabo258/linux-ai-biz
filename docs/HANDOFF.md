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

State: 277 tests pass; 49 regulations / 65 policies validate.

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

The full Jarvis screen (2026-10-09):
- live work per node: `activity.py`, `/api/activity`;
- working panels: Scout search/inspect/report, model Test, draft editing (`ui/screen.py`);
- timeline from the audit chain (`/api/timeline`);
- Mission Control views inside (`/api/mc/<view>`);
- phone ring with pinch and swipe;
- opt-in wake word and alerts;
- light theme, zoom, a key for every button.

Tests were written first: `tests/test_jarvis_live.py`. The page passes `bau a11y lint`.

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

## First message to paste into Claude Code

> Read CLAUDE.md and docs/HANDOFF.md. Then help me do step 1 of the handoff: check that
> VirtualBox is installed and that the three files are in my Downloads folder, run
> vm\create-vm.ps1 (or create-vm.sh on Mac/Linux), and walk me through the install inside
> the VM. If the script fails against real VirtualBox, fix it, run the repo checks, and
> open one PR with the fix.
