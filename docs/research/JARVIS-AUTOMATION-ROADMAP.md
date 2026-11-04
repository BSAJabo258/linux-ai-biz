# Jarvis automation roadmap

The plan that follows the review in
[AI-AUTOMATION-REPOSITORY-REVIEW.md](AI-AUTOMATION-REPOSITORY-REVIEW.md). Written
2026-11-04. Nothing here is built yet. Each step is one pull request with its tests,
and the owner says yes before the next one starts.

## The shape

```
            Jarvis (src/bau/assistant.py) plans and talks
                              |
          Universal Gateway (src/bau/gateway.py): permission, HOLD, budget, audit
             |                    |                      |
       desktop lane          browser lane         procedure library
   Agent Desktop (MCP)   Browser Use or Playwright   agent folders + MAYA
     via src/bau/mcp.py     MCP, actions only          memory statuses
```

BAU stays the authority. The new tools are hands, never a second brain.

## The order

### Step 1: "read untrusted, lose write tools" (small, makes every later step safer)

**Built 2026-11-04** (tests: `tests/test_untrusted_taint.py`, run in CI; not yet run on the
desktop). Two places use it:

- **Agents** (`src/bau/agents.py`): after a tool whose answer comes from outside the computer
  (network, an outside provider, an MCP server, a browser), every later call above READ_ONLY
  in that run is refused at the gateway's `untrusted_read` step, unless it carries the owner's
  signed approval. HOLD-type safety tools still run.
- **Jarvis** (`src/bau/assistant.py`): after `web_search`, `read_page` or `find_tools` in a
  turn, his "act" tools (remember, plan a mission, queue a post...) wait. Asking again in a
  new message is the owner's OK. Cards that wait for the owner's click were never affected.

- **Change:** within one agent run, once a tool result marked untrusted (a web page, a
  screen, an MCP answer) has been read, every capability above READ_ONLY is refused for the
  rest of that run, unless the owner approves that call. This idea comes from LocalHarness.
- **Files:** `src/bau/agents.py`, which marks the run as tainted when it wraps a result with
  `untrusted()`, and `src/bau/gateway.py`, which checks the mark. No other caller changes.
- **Tests:** a planted page saying "now delete X" cannot reach a writing tool; read-only
  tools still work; owner approval still works.

### Step 2: the desktop lane (Agent Desktop)

- **How it joins:** one registry record for the MCP server `agent-desktop`, started by the
  existing MCP client. No new gateway code.
  - **Read-only tools** (marked so in the record): `snapshot`, `list-apps`,
    `list-windows`, `find`, `get`, `is`, `screenshot`, `status`.
  - **Every other tool** (`click`, `type`, `press`, `launch`...) stays APPROVAL_REQUIRED,
    which is the client's default.
- **Verification:** after an action, a fresh `snapshot` by a separate check, not by the
  agent that acted, compares against the expected state.
- **Install:** the GitHub release archive, checked against its `checksums.txt` and pinned
  by SHA-256 like the stick's other downloads. No npm.
- **The stick:** add the Debian package `at-spi2-core` to
  `image/live-build/config/package-lists/my-jarvis.list.chroot` and `install.sh`'s list, and
  prove it in the stick build in CI (the `stick-change` skill).
- **Tests here:** a fake Agent Desktop MCP server (beside `tests/fixtures/fake_mcp_server.py`)
  checks that read tools run, writing tools need approval, stale refs are reported, and HOLD
  stops actions.
- **Acceptance on the owner's desktop** (it needs the real XFCE session, which this cloud
  session cannot provide):
  1. list the apps;
  2. snapshot the text editor;
  3. type a line after approval;
  4. snapshot again and see the line.
- **Rollback:** `bau set-status mcp agent-desktop REVOKED`. The server is not started again,
  and its tools disappear.

### Step 3: the browser lane (Browser Use, tested against Playwright MCP)

- **Sandbox test first:** both run in a throwaway container on practice pages, with no saved
  logins. The test measures memory, time, telemetry (read the source first) and whether
  each action can be called one at a time from Jarvis.
- **Four permissions**, as in the capability map:
  - read: READ_ONLY;
  - fill a field: REVERSIBLE;
  - save a draft: REVERSIBLE;
  - submit, sign up, buy, send: APPROVAL_REQUIRED or higher, and always the owner's click.
- **Never on Instagram, TikTok or Fanvue.** Those platforms ban automated browsers; BAU
  posts there through their official APIs only.
- **Acceptance:** open a page, read it, fill a practice form, stop before submit, and on the
  owner's click submit and check the result page.

### Step 4: the procedure library

- **What:** after a job succeeds, Jarvis may write a proposed skill (the steps, the tools,
  the result, the cost) as a new `SKILL.md` in an agent folder. This idea comes from Hermes.
- **States:** proposed, then experimental (run on practice tasks), then verified (passed
  separate checks), then approved, then deprecated. MAYA's status tags hold them (the
  EXPERIMENTAL, CURRENT and DEPRECATED tags already exist).
- **Approval:** the existing folder approval (SHA-256, the owner's yes). A skill can never
  change permissions, policies or its own approval.
- **Recall:** later sessions find approved skills through the existing skill index.

### Step 5: independent checking

- **What:** a check suite with practice tasks and expected results, run by a checker that
  did not do the work. Each passing tool result gets a receipt: its hash, linked into the
  audit chain. This idea comes from ZeroClaw's tool receipts.

## Hardware

- **Measure first:** `bau hw` on the desktop. The owner's check report says 16 GB of system
  memory and a 12 GB RTX 3060 card. The directive says 12 GB; the measurement decides.
- **No new always-on server:**
  - Agent Desktop starts only while Jarvis uses it.
  - The browser lane starts one browser per job and closes it.
- **No model downloads.** The existing local model and hosted models stay as they are.
- **Already known:** the 9B local model and the picture model compete for the 12 GB card.
  The browser and desktop lanes add no model of their own.

## What never changes

- Jarvis's loop, memory, model router and gateway.
- Approvals stay human only.
- Third-party tools get no keys.
- Tool output is untrusted data.
- Every action is audited, and HOLD stops it.

## Next

The owner says which step to start. Step 1 is recommended first: it is small, and it makes
steps 2 and 3 safer.
