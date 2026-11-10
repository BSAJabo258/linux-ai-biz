# The capability map: what Jarvis can do, what's missing, and what to build next

Jarvis's abilities are split into layers, from thinking to making money. For each layer
the map says three things:

- **what BAU already has** (with the file that does it);
- **which open-source tools could fill the gap**, all researched in the toolbox with
  their sources, and **how** each would join BAU;
- **the rules that stay in force**, so a new ability never comes with new authority.

See it any time:

```bash
bau toolbox map                    # every layer, and the build order
bau toolbox map --layer web        # one layer: its tools, licences, caveats, evidence
```

Or ask Jarvis: "What can you do, and what's missing?"

## How a tool joins BAU

| Plan | Meaning |
|---|---|
| direct | used as it is (it already fits BAU's rules, for example a local library) |
| adapter | wrapped behind a BAU adapter, so BAU's gateway, audit log and approvals stay in charge |
| later | worth it, not yet (riskier, heavier, or waiting for something else first) |
| skip | BAU already does this job; adding it would mean two of the same thing |

Every tool in the map is a **claim** until Repo Scout inspects it
(`bau toolbox check NAME`) and a test passes on your cloud server. Nothing is installed
from the map.

## The layers

| # | Layer | Today | Next step |
|---|---|---|---|
| 1 | Web interaction | gap | the browser lane: read, fill, draft, submit as four separate permissions; submit is your click |
| 2 | Connectors and MCP | partial | search the MCP Registry from Scout; a health check per connector |
| 3 | Computer use | gap | one isolated desktop on the cloud server, practice tasks only |
| 4 | Workflows and saved skills | partial | save each finished browser task as a procedure with its success rate and cost |
| 5 | Seeing documents and screens | gap | read PDFs and scans locally, on the laptop (planned, not built yet) |
| 6 | Checking the work | partial | a practice-task suite with expected results |
| 7 | Teams of agents | partial | a coordinator that picks the smallest team for each job |
| 8 | Coding and self-improvement | partial | Jarvis opens a draft pull request; you review and merge |
| - | Thinking and planning models | have | local model for routine work, Claude or a hosted model for hard jobs |
| - | Planning | have | missions, decisions, the opportunity scorer |
| - | Memory | have | Second Brain, memory lane, chat library |
| - | Media | have | studio, series engine, provenance on every file |
| - | Business results | have | ledger, results tracker, publishing on your confirm |

## Rules that come with every new ability

- **Web pages, documents and screenshots are untrusted data.** Instructions found in them
  are never followed.
- **Reading, filling in, saving a draft and submitting are four different permissions.**
  Submitting, paying, sending and signing up are always your click.
- **New abilities start in isolation:** a browser or desktop on the cloud server with no
  saved logins. Giving an agent your own logged-in browser comes last, if ever.
- **The agent that did a job never marks it as passed.** A separate check or you do.
- **Money is counted when it's collected.** Each money idea gets a fixed trial budget and
  stops if nobody pays.

## Your build choices (2026-10-12)

- **USB: both.** Today there are two single-stick images:
  - the live USB (`my-jarvis-*.iso`) runs Jarvis from the stick with encrypted storage;
  - the installer (`bau-one-debian-*.iso`) installs encrypted Debian and carries the BAU
    files, so it needs no second stick.

  The plan is to put both on the same 128 GB stick: Debian's installer inside the live
  image, so one stick offers "Try My Jarvis" and "Install BAU on this laptop".
- **Storage: 128 GB stick.** The image uses under 1 GB; about 125 GB is left for encrypted
  storage, data, backups and a few local models.
- **Compute: hybrid.** A small local model for routine work, Claude or a hosted model for
  hard jobs, and the cloud server running Jarvis around the clock.
