# Repository Intelligence (Repo Scout)

Jarvis can now look for open-source projects that provide a capability, gather evidence
about each one, and rank them, **without installing or running any of them**. This is the
spec's principle, *discover broadly, evaluate rigorously, integrate selectively*, built on
BAU's existing intake pipeline (Sentinel and the sandbox) rather than beside it. The audit
done before this work is in [baseline-audit.md](baseline-audit.md).

## Use it

```bash
bau scout find "simulate customers to test a business idea"   # search, record, rank
bau scout report                       # plain-words report of the latest search
bau scout list                         # every candidate so far, best first
bau scout show OWNER/NAME              # everything recorded about one
bau scout inspect OWNER/NAME           # download it into quarantine and scan it (runs nothing)
```

Or ask Jarvis: "find open-source tools for customer simulation". The **Scout** dot on the
Jarvis screen shows the latest search and the best candidates.

Without a key, GitHub allows 10 searches a minute, so a six-search run takes about 40 seconds.
To raise the limit, put a GitHub token with no scopes in `GITHUB_TOKEN`: as a Codespaces
secret, in `.env` for Docker, or in `/etc/bau/models.env` on the laptop. The token only
raises the limit; nothing a candidate repository runs ever sees it.

## How it works

```
request ──> plan (several phrasings) ──> GitHub search, paced, failures recorded
        ──> merge + de-duplicate (forks point to their upstream)
        ──> evidence: claims (description, topics, README)  |  inspection (Sentinel)  |  tests (sandbox)
        ──> gates (licence, security, tested) + score on known facts only
        ──> candidates.json + runs.jsonl + audit chain ──> report / Jarvis / screen
```

| Spec module | Where | What it does now |
|---|---|---|
| A. Repository intelligence | `scout/plan.py`, `scout/github.py`, `scout/__init__.py` | One request becomes a *research spectrum*: the request's own keywords, plus alternative names for the capability from 15 facets (customers, simulation, business, agents, coding, memory, video, image, audio, music, browser, scheduling, research, inference, testing), plus a few model phrasings if a model is approved. Model phrasings are cleaned and tagged. GitHub search runs read-only and paced under its rate limit. A refused or failed search is recorded as **failed**, never as "nothing found". Fork upstreams are looked up and forks of a result are marked duplicates. READMEs are read for the leading candidates |
| B. Candidate registry and scoring | `scout/evaluate.py`, `data/scout.yaml`, `BAU_HOME/scout/candidates.json` | Each record keeps **claimed** (description, topics, README signals), **inspected** (Sentinel scan of a quarantined copy) and **verified** (test status) apart. Scores use the spec's dimensions with configurable weights. A dimension with no evidence scores 0 and is listed under `unknowns`. *Evidence coverage* says how much of the score rests on facts |
| Licence and security gates | `evaluate.py` | These are gates, not points. A licence that forbids commercial use (NC, BUSL, SSPL, Elastic, PolyForm NC), a Sentinel rejection, an archived upstream or a failed test **rejects** a candidate whatever its score. Nothing is *eligible* until its licence has been reviewed, its security inspected and its tests passed. Discovery alone never makes anything eligible. A README that says "non-commercial" or "research only" overrides a permissive licence declared to GitHub and sends it to review |
| E. Isolated validation | existing `security/sentinel.py` + `sandbox.py`; new `bau scout inspect` | `inspect` makes a shallow clone into `BAU_HOME/scout/quarantine/`. The clone allows no hooks, LFS filters, submodules, credential prompts or inherited secrets, and HTTPS only. Sentinel then scans it statically and heavy dependencies (torch, CUDA and the like) are read from its requirement files. Running its tests is the existing sandbox stage (`bau sandbox`), which needs Podman and an approval |
| G. Learning record | `BAU_HOME/scout/runs.jsonl`, audit events `scout.run`, `scout.inspected` | Every run records its plan, each search and its result or failure, notes, and the ranking. These are the data for tuning queries and weights later |
| Jarvis | `assistant.py` tools `find_tools` (act) and `scout_results` (read); `overview.py` Scout node | Jarvis can search and report. It has no tool to inspect, approve or install |

### Core versus optional

The scout is imported only when used. A test checks that starting the CLI, Jarvis, the
overview and the Jarvis server loads no `bau.scout` module. It adds no dependencies: it is
stdlib plus PyYAML, which BAU already uses.

| After this upgrade | Baseline | Now |
|---|---|---|
| Tests | 246 in about 30 s | 259 in about 30 s |
| `import bau.cli` | about 0.11 s | about 0.07 s (unchanged, within noise) |
| Mission Control memory | about 25.5 MB | about 25.6 MB |
| New code on disk | | 44 KB (`src/bau/scout/`) |

## Not built yet (next phases, one PR each)

1. **Validation reports from the sandbox (Phase 4).** Run a candidate's own tests in
   `bau sandbox` after approval and write the result back to `validation`. That is what
   moves a candidate from *not tested* to *passed* or *failed*. It needs Podman, which the
   codespace does not have by default.
2. **Licence review record.** A human records "licence reviewed" with a reference. Until
   then every candidate shows *licence declared but not reviewed*.
3. **Adapter interface (Module D).** A common `CapabilityAdapter` (describe, check, run
   with timeout, health, normalised result) for the first real integration.
4. **First real integration (Phase 6).** One small, permissively licensed, low-risk tool,
   end to end.
5. **Composition (Module C).** Evaluating combinations comes after single integrations
   work.
6. **More sources.** Package registries and model registries, as further adapters beside
   `scout/github.py`.

## Branch protection (the owner sets this once)

On github.com, go to the repo, then **Settings → Rules → Rulesets → New branch ruleset**:

1. Target the default branch (`main`).
2. Turn on **Require a pull request before merging**. With one owner, set the required
   approvals to 0. GitHub does not count your own approval.
3. Turn on **Require status checks to pass** and add `test (3.11)` and `test (3.13)`.
4. Turn on **Block force pushes**.
5. Turn on **Restrict deletions**.

Leave the bypass list empty unless you choose otherwise. After this, nothing reaches
`main` without a PR and green CI, including work by Claude.

## Facts used

GitHub REST search API, checked 2026-10-09 at docs.github.com/en/rest/search/search:

- `GET /search/repositories` returns up to 100 per page and 1,000 per search.
- The search limit is 10 requests a minute without a token and 30 with one.
- API version header `2026-03-10`.
- The search items carry the license `spdx_id`, `fork`, `archived`, `pushed_at` and
  `size` fields.

The details are recorded in `scout/github.py`. GitHub is a research source here, not a
publishing platform, so there is no `examples/platform-*.yaml` record: BAU never posts to
GitHub through the scout.
