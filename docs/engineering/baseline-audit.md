# Baseline audit before Repo Intelligence (2026-10-09)

This is a record of where the repository stood before the *Repository Intelligence*
upgrade, so that problems the upgrade causes can be told apart from problems that were
already there. Every figure below was measured, not assumed.

## Repository

| | |
|---|---|
| Repository | `bsajabo258/linux-ai-biz`, default branch `main` |
| Baseline commit | `fe7be92` (`main` after PR #26) |
| Working tree | clean |
| Language | Python only (3.11 and 3.13 in CI); shell for the installer and image |
| Packaging | `pyproject.toml` (setuptools). One runtime dependency: `PyYAML>=6.0`. Extras: `dev` (pytest, ruff), `claude` (anthropic). There is no lockfile: BAU is stdlib-first by design |
| Entry points | `bau` (`bau.cli:main`, with `cli_ext.py`), `jarvis-storage` (`bau.live:main`) |
| Interfaces | Mission Control (`bau ui`, port 8765), Jarvis (`bau jarvis`, port 8766). Both are stdlib HTTP servers bound to 127.0.0.1 |

## Architecture that already covers parts of the specification

The specification describes several modules. Some of them already exist under other names,
so they were reused instead of being written a second time:

| Specification | Already in BAU |
|---|---|
| Isolated validation (Module E) | `security/sentinel.py` does a static intake scan and never executes anything: licence files, install hooks, risky code patterns, embedded secrets, surfaces (MCP server, agents, Docker, binaries). `sandbox.py` runs code in rootless Podman with no network, a read-only root, all capabilities dropped, and memory, CPU and PID limits. Intake states run DISCOVERED → … → QUARANTINED → SANDBOX_TESTED → … → APPROVED |
| Licence review | `sentinel.COMMERCIAL_OK` / `COPYLEFT` / `NONCOMMERCIAL` sets and licence text detection |
| Capability registry | `registry.py` `CapabilityRegistry` holds models, agents, providers and tools *already admitted* to BAU, with benchmark-before-approval. Discovered candidates are deliberately kept in a **separate** store (`scout/`), so nothing found on the internet can appear routable |
| Human approval | Approvals are SSH-signed by a human (`bau approve`). No agent or model may approve |
| Experiment record | The audit chain (`audit.py`, hash-chained, HMAC-signed) |
| Secrets | Keys live in `/etc/bau/*.env`, `.env` (gitignored) or Codespaces secrets. `bau secrets .` runs in CI |

## Tests and checks at the baseline

| Check | Result |
|---|---|
| `python -m pytest -q` | **246 passed**, 0 failed, about 30 s |
| `ruff check .` | clean |
| `bau reg validate` | valid (49 regulations, 65 policies) |
| `bau secrets .` | no findings |
| shellcheck (installer, image, docker, vm scripts) | clean in CI |
| Known failing tests | none |
| Known build problems | none in CI. The live ISO build needs Docker and about 15 GB of disk, so it runs only on demand (`build-live.yml`) |

## CI (`.github/workflows/`)

| Workflow | Trigger | Notes |
|---|---|---|
| `ci.yml` | push and pull_request | Python 3.11 and 3.13 matrix: lint, secret scan, registry check, tests, shellcheck, payload build. `permissions: contents: read`. It had **no job timeout and no concurrency group**, and both triggers fire on a PR branch, so every PR ran the suite twice |
| `docker.yml` | push and PR | Image build; has a timeout and a concurrency group |
| `build-usb.yml`, `build-live.yml` | manual or tag | Long builds with timeouts |

Third-party actions are pinned to major tags (`actions/checkout@v4`, `actions/setup-python@v5`,
`docker/*`), not to commit SHAs.

## Resources (measured in the build container: 4 CPUs, 16 GB RAM)

| | Baseline |
|---|---|
| `import bau.cli` | about 0.11 s |
| Mission Control server resident memory | about 25.5 MB |
| Mission Control first response | about 2 ms |
| Test suite | about 30 s |
| Codespace definition | `hostRequirements.cpus: 2`. The owner's codespace runs 4 cores and 16 GB |

## Concerns found

1. **Branch protection is not verified.** The session that built BAU merged its own PRs
   after green CI, with the owner's standing permission. There are no required reviewers
   because there is one owner. Recommended settings are listed under *Branch protection* in
   [repo-intelligence.md](repo-intelligence.md). The owner sets them; the build session
   cannot.
2. **CI ran twice per PR and had no timeout.** Fixed in this upgrade: a 20-minute job
   timeout and a concurrency group that cancels superseded runs.
3. **Actions are pinned to tags, not SHAs.** Left as is, because pinning means looking up
   each SHA from the action's own repository. Recommended as a follow-up.
4. **There is no `.env.example`.** Keys are documented per guide (`CLOUD-TEST.md`,
   `INSTALL.md`, `docker/README.md`), so none was added.
5. **The build container cannot reach GitHub search.** Its network is limited to this
   repository's endpoints. Live discovery has therefore been exercised only against a
   stand-in. The first real search is the owner's (see the guide).
