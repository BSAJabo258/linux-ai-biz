# ARCHITECTURE_RFC.md

# Executive Controller RFC — ARCHITECTURE_RFC

Status: Proposed (prototype scaffold)

Purpose

This RFC describes a small, well-scoped scaffold for an "Executive Controller" and a minimal Adapter interface for the linux-ai-biz project. The goal is to provide a safe, testable foundation for task lifecycle management and adapter-based capability invocation without replacing or duplicating existing durable job/persistence systems already present in the codebase (see src/bau/jobs.py).

Scope and constraints

- This change is intentionally small and additive. It must not replace or rewrite existing components.
- The prototype is not production-grade: it uses an in-memory queue unless an existing persistent JobStore (src/bau/jobs.JobStore) is injected.
- No runtime side-effects: the controller exposes explicit async APIs and does not spawn hidden background workers or automatic retries.
- All adapters are treated as external capability providers and invoked through a minimal contract. Adapters themselves are out-of-process concepts; the repository includes only an interface and registry.

Design overview

Key concepts

- TaskContract
  - A small dataclass describing the task: mission_id, objective, agent, model, tools, budget, risk, and scope metadata.
  - Validation is lightweight and deterministic.

- ExecutionResult
  - Structured result returned by an adapter run: success (bool), status (string), artifacts (list), errors (list), and evidence (dict).

- ExecutiveController
  - API surface (async): create_task(contract) -> task_id; validate_task(contract) -> bool; dispatch(task_id, adapter_id) -> ExecutionResult; cancel(task_id); get_status(task_id) -> Job-like status.
  - Dependency-injected collaborators: AdapterRegistry and optional persistent JobStore (src/bau/jobs.JobStore). If a JobStore is provided it is used for checkpointing; otherwise controller uses an in-memory JobStore for the prototype.
  - No background threads, no automatic retries, no hidden network calls.

- AdapterBase and AdapterRegistry
  - AdapterBase: abstract base describing async run(contract, context) -> ExecutionResult semantics and capability tags.
  - AdapterRegistry: register/get adapters, prevent duplicate registration, lookup by capability.

Integration with existing code

- Jobs and persistence
  - The repo already includes src/bau/jobs.Job and JobStore. The ExecutiveController accepts an optional JobStore instance to checkpoint Job objects using the existing durable mechanism. Passing a JobStore is recommended for any production scenario.

- Sandbox, governor, runtime
  - Existing sandboxing and verification components (src/bau/sandbox.py, src/bau/governor.py, src/bau/runtime.py) are left unchanged. Adapters and future integrations should reuse these components when executing untrusted or network-facing work.

- Model & capability registries
  - This RFC defines adapter and model registry interfaces (minimal). The repository already contains src/bau/registry.py and src/bau/models; the new Registry helpers are intentionally small and meant to interoperate rather than duplicate functionality. A future step will migrate or adapt existing registries to a shared interface if warranted.

Task lifecycle

1. create_task(contract) — validate contract and persist a Job (if JobStore provided) or keep in-memory.
2. dispatch(task_id, adapter_id) — validate adapter exists, ensure task is in a dispatchable state, pass a context (including a should_cancel callable) to adapter.run and await its result.
3. On completion, checkpoint job status (COMPLETED or FAILED) and record structured ExecutionResult in job.artifacts/evidence.
4. cancel(task_id) — mark job status CANCELLED; adapters can observe should_cancel and stop cooperatively.

Security, permissions and approvals

- This RFC does not implement a permission enforcement runtime. Instead it defines the concept of a TaskContract that includes the declared tools and a risk/budget hint. Enforcement is expected to be performed by the sandbox/adapters and by the Governor component.
- Approval gates remain human-only per repository policy. The ExecutiveController will transition tasks into WAITING_FOR_APPROVAL if asked; the approval flow itself remains outside this scaffold.

Limitations and next steps

- Persistence: in-memory JobStore used when no persistent JobStore is injected. Production use must inject src/bau/jobs.JobStore or another durable store.
- Scheduling: no scheduler or worker pool is included. This scaffold runs adapters synchronously under caller control. A future component (Task Runner / Worker Pool) will launch and monitor background workers and provide durable scheduling.
- Observability: the RFC recommends structured JSON events and integration with existing logging but the scaffold only emits structured results returned by adapters.
- Adapter integration: adapters for real systems (LangGraph, OpenCode, Aider, llama.cpp, vLLM, browser agents) are not included here. The next work will implement adapters as thin wrappers that call sandboxing and existing runtime helpers.

Acceptance criteria for this PR

- Added files are small, additive, and safe.
- New unit tests cover task creation, validation, dispatch success/failure, cancellation, and adapter registration semantics.
- No modification to existing runtime behavior, installer scripts, or heavy build pipelines.
- CI runs the new tests and reports results.


