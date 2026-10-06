# Handoff: BAU/BSA - state on 2026-10-05

For Claude Code in VS Code on the owner's computer, picking up from the cloud session that
built BAU. Read `CLAUDE.md` for layout, commands and the rules that must not be broken.

## What exists (all merged to `main`)

| PR | What |
|---|---|
| #1-#4 | USB installer (two sticks), control plane, compliance engine, Governor, TikTok review-and-post, Second Brain, GitHub Actions USB build (`build-usb.yml`) + Codespaces |
| #5 | Jarvis: spoken briefing, conversation with memory, tools, owner-confirmed actions, voice HUD (`bau jarvis`) |
| #6 | Publishing hub (`publishing.py`) with TikTok + YouTube adapters; made-for-kids rules (`kids.py`, `policies/kids_content.yaml`); `kids_channel` factory |
| #7 | Docker test drive, VirtualBox rehearsal scripts (`vm/`), GLM-4.7-Flash free local fallback, `bau models bench` |

State: 172 tests pass; 49 regulations / 65 policies validate. Main = `619fa73`.

## What was verified, and how

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
