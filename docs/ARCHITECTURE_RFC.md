# Executive Controller RFC

Status: prototype scaffold. Not wired into Jarvis yet.

This RFC describes the first, deliberately small step towards an executive controller and a
modular adapter layer. It adds a coordination layer *below* the existing
`src/bau/jarvis.py` mission lifecycle: one task, one adapter, one existing
`src/bau/jobs.Job`. It does not replace Jarvis, the JobStore, the Governor, the
Gateway, the sandbox, the policy engine or the model registry.

## Scope

- Additive only. No existing module changes behaviour.
- Synchronous: `dispatch` runs the adapter in the caller's thread. The controller
  adds no event loop, scheduler, worker pool, retry or background thread.
- Adapters are trusted in-process callables in this prototype. They are not
  sandboxed by the controller and are not a substitute for the Gateway.
- No real adapter ships in this change. The package contains the interface,
  the registry and focused tests.

## Files

| File | What |
|---|---|
| `src/bau/executive.py` | `TaskContract`, `ExecutiveController`, `InMemoryJobStore` |
| `src/bau/adapters/base.py` | `AdapterBase`, `AdapterRegistry`, `ExecutionContext`, `ExecutionResult` |
| `src/bau/adapters/__init__.py` | public exports |
| `tests/test_executive.py` | focused unit tests |

## TaskContract

`TaskContract` mirrors the fields the existing `jobs.Job` already has:
`mission_id`, `objective`, `agent`, `model`, `tools`, `budget_usd`, `risk`.

Validation is deterministic and returns a list of human-readable problems
(`validate_task(contract) -> list[str]`; empty means valid). It checks required
strings, a known `blast.LEVELS` risk, a finite non-negative budget and a
non-repeating list of tool names. "Scope metadata" is not part of this
prototype: the persisted `Job` is the task record, and an adapter that needs
more context can put it in its own arguments or evidence.

`tools` and `budget_usd` are declarations recorded on the job. The controller
does not check them, grant them or spend against them.

## ExecutionResult and ExecutionContext

- `ExecutionResult(status, artifacts, errors, evidence)` where `status` is one
  of `COMPLETED`, `FAILED`, `CANCELLED`. `success` is a derived property, not a
  second stored field, so the two cannot disagree.
- `ExecutionContext(task_id, mission_id, should_cancel)` is data only. An
  adapter may call `context.cancelled()` to stop cooperatively.
- `evidence` is returned to the caller and is **not** persisted by the
  controller. Only `artifacts` and `errors` are recorded on the job.

## Persistence

The controller never constructs `jobs.JobStore` itself, because its constructor
creates directories and is not side-effect free.

- The default is `InMemoryJobStore`, a `JobStore` subclass that writes nothing.
  It overrides `__init__` (no directory is created), `checkpoint`, `load` and
  `all`; it inherits `create` and `step_done`. Its `checkpoint` repeats
  `JobStore`'s check against `jobs.STATES`, so an unknown status is refused in
  memory as it is on disk. Jobs live only as long as the controller object.
- A durable store is injected explicitly:
  `ExecutiveController(store=JobStore(home), ...)`.
- The controller relies on only three methods: `create`, `checkpoint` and
  `load`. That is the `JobBackend` protocol; `JobStore` satisfies it
  structurally.

A job is created with no remaining steps because the controller's only step is
the dispatch itself. The controller sets `RUNNING` before calling the adapter
and `COMPLETED` / `FAILED` / `CANCELLED` afterwards, always through
`checkpoint`.

## Lifecycle

1. `create_task(contract) -> task_id` validates the contract and persists a
   `PENDING` job. A `HIGH` or `CRITICAL` risk creates it as
   `WAITING_FOR_APPROVAL` instead.
2. `get_status(task_id) -> jobs.Job` loads the persisted job; there is no
   parallel status model.
3. `dispatch(task_id, adapter_id, approval_ref=None) -> ExecutionResult`:
   - refuses a terminal task;
   - for `WAITING_FOR_APPROVAL`, refuses without an `approval_ref`; with one, it
     records the reference (unverified, see below) and runs. The reference is
     saved only once the run starts: a HOLD or an unknown adapter discards it;
   - refuses `PAUSED`, `RUNNING` and other non-dispatchable states;
   - asks an injected `hold()` (pass `governor.hold_reason`) before running and
     refuses while BAU is on HOLD;
   - loads the adapter (an unknown id leaves the task untouched), sets
     `RUNNING`, calls `adapter.run`, records artifacts/errors and maps the
     result status onto the job.
4. `cancel(task_id) -> jobs.Job` marks a non-terminal task `CANCELLED`. It is
   idempotent on a terminal task. An adapter already running is not
   interrupted; it observes `should_cancel` and is expected to stop.

An adapter exception (or a return value that is not an `ExecutionResult`) is
recorded as `FAILED` with the error text, unless the task was cancelled during
the run (it then stays `CANCELLED`, with the error recorded); `dispatch` returns
a failed result rather than crashing.

## Approvals, permissions and security

This scaffold does **not** enforce permissions, approvals, data boundaries,
budgets, tool allow-lists or sandboxing, and it makes no claim to.

- Approval gates are human-only. The controller has no `approve` method and
  cannot mint, verify or infer an approval. For a `HIGH`/`CRITICAL` task it
  records a reference the caller supplies *after* a human approved (for
  example via the existing `bau approve` flow). Verifying that reference is
  outside this module.
- The Universal Gateway (`src/bau/gateway.py`) remains the only path from an
  agent to a capability: registration, agent tool lists, HOLD, permission
  levels, approval, network trust, data boundaries, blast radius and budget.
  An adapter that calls a tool must go through it.
- `src/bau/sandbox.py` is unchanged and is not invoked here. Running untrusted
  code remains the adapter's job, through the existing sandbox.
- The optional `hold` callback is the only Governor awareness the controller
  has. When it is omitted, the controller does not read `BAU_HOME` and does not
  consult the hold state. Jarvis should pass `governor.hold_reason`.
- `src/bau/registry.py` is not duplicated or replaced. Declared models and
  tools are recorded, not routed; model routing stays with the existing
  registry and router.

## Cancellation

Cancellation is cooperative and single-process. `cancel()` records the state;
the next `context.cancelled()` call returns true. A cancel recorded while the
adapter runs wins over the adapter's own result: the job stays `CANCELLED` and
any partial artifacts are kept. It also wins if the adapter then raises; the
error is recorded on the job. There is no preemption and no timeout: an adapter
that never checks `cancelled()` runs to its end.

## CI and tests

The repository's existing `.github/workflows/ci.yml` already runs
`ruff check src tests`, the full pytest suite, `bau reg validate`, the secret
scan and shellcheck on Python 3.11 and 3.13 for every push and pull request.
This change adds no second workflow: it would duplicate that coverage, and the
earlier `exec-ci.yml` both referenced files that did not exist and masked lint
failures with `|| true`.

`tests/test_executive.py` covers creation and validation, the in-memory default
(no filesystem writes), durable injection, dispatch success/failure/adapter
faults, unknown adapters, registry duplicates and capability lookup, approval
waiting and the recorded reference, HOLD refusal, cancellation before and
during a run (including an adapter that raises after the cancel), terminal
tasks, the in-memory store's status check, and contract reconstruction from the
job.

## Limitations and next steps

- No verification of an adapter's claim: a job marked `COMPLETED` means the
  adapter said so. Jarvis's verification and evidence package remain separate.
- No scheduler, worker pool, retries, timeouts or restart recovery beyond what
  `jobs.recover()` already provides.
- No real adapters, no CLI command and no Jarvis wiring yet.
- The contract has no scope/context field; add one only when an adapter needs
  it, and persist it deliberately rather than keeping hidden controller state.

## Acceptance criteria

- The new files exist and are additive; no existing behaviour changes.
- `ruff check src tests` and the full pytest suite pass on Python 3.11 and 3.13
  through the existing `ci.yml`.
- The controller reuses `jobs.Job`, `JobStore` and the Governor's hold reason
  instead of duplicating them, and writes nothing unless a store is injected.
- The RFC claims nothing the code does not do.
