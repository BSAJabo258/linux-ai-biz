# BAU/BSA Architecture Map

Status: draft

Purpose

This document is the source-of-truth map for the repository as it currently exists. It defines the existing components, their responsibilities, and the integration points that should be extended rather than replaced. The goal is to keep the system coherent as it evolves toward the Jarvis universal AI operating environment.

Scope

This map reflects the repository state in the current codebase and intentionally focuses on existing functionality that should be preserved. It does not claim that the full Jarvis vision is already implemented. Its purpose is to establish the baseline before we add a minimal executive controller scaffold and adapter interface.

Repository structure overview

- src/bau/
  - Core package for BAU/BSA control plane.
  - Contains the control logic, governance, model and registry logic, user-facing services, and business-domain functions.
- tests/
  - pytest-based verification suite.
- installer/
  - OS and payload generation for Debian installation and USB workflows.
- docker/
  - Docker test-drive and local containerized environment.
- image/
  - Live USB image generation and related configuration.
- vm/
  - VM rehearsal scripts and cloud/local test infrastructure.
- docs/
  - Engineering and user docs.
- .github/workflows/
  - CI and release automation.

System-level responsibilities by module

1. Core control plane and runtime

- src/bau/__init__.py
  - Package version and package-level description.
  - Establishes the BAU control plane as the root identity.

- src/bau/runtime.py
  - Runtime coordination and status surfaces.

- src/bau/status.py
  - System status reporting and readiness checks.

- src/bau/home.py
  - BAU_HOME directory layout and persistent state management.
  - Canonical runtime directory for state, memory, jobs, approvals, evidence, and audit artifacts.

- src/bau/jobs.py
  - Existing job lifecycle abstraction.
  - Contains Job and JobStore checkpoints, workflow state transitions, network recovery logic, and budget controls.
  - This is the canonical persistence and lifecycle primitive in the current repo.

2. Governance, permissions, approvals and compliance

- src/bau/governor.py
  - Watchdog / hold / quarantine / resume logic.
  - Policy enforcement and operating adjustments.

- src/bau/sandbox.py
  - Execution isolation boundaries for tasks and actions.

- src/bau/policy.py
  - Policy engine and logic.

- src/bau/regulations.py
  - Regulation registry and public policy data.

- src/bau/decision.py
  - Decision logic and decision-type handling.

- src/bau/audit.py
  - Audit and evidence chain support.

- src/bau/evidence.py
  - Evidence and proof artifacts.

- src/bau/keys.py
  - Key management and import/export support.

- src/bau/security/
  - Security-specific components and modules.

These modules form the governance boundary and should not be bypassed by any executive layer.

3. Capability registry and model/resource registration

- src/bau/registry.py
  - Current capability registry validating models, agents, MCP objects, repositories, and providers.
  - Defines required fields, status transitions, trust levels, and routing rules.
  - This is the clearest current registry abstraction in the repo.

- src/bau/models/
  - Model provider and routing logic.
  - Local and remote inference providers are handled here.

- src/bau/toolbox.py
  - Tool registry and tooling discovery layer.

- src/bau/agentfolders.py
  - Agent-as-folder workflow model.

- src/bau/gateway.py
  - Capability access gateway and structured entryway into tools and accounts.

These components are the likely integration points for a universal harness and capability registry without duplicating the existing registry logic.

4. Jarvis, team, assistant, and user interaction

- src/bau/assistant.py
  - Assistant and user-facing reasoning model.

- src/bau/jarvis.py
  - Jarvis user experience and orchestration surface.

- src/bau/team.py
  - Team composition and governance of model roles.

- src/bau/supervisor.py
  - Supervisory oversight and coordination. 

- src/bau/usage.py
  - Usage tracking, model cost, and daily limits.

- src/bau/brain.py
  - Memory and knowledge graph concepts.

- src/bau/chats.py
  - Conversation storage and retrieval patterns.

- src/bau/memory.py
  - Memory model and retention logic.

These form the user-facing and operational intelligence layer. They should be treated as the runtime context and orchestration surface, not as an external framework to be replaced by a second, independent orchestration engine.

5. Business and work execution functions

- src/bau/factories.py
  - Business factory model.

- src/bau/workspace.py
  - Workspace-based workflows and staged work outputs.

- src/bau/series.py
  - Story/series generation workflows.

- src/bau/studio.py
  - Media / video production workflow.

- src/bau/results.py
  - Results tracking, profits, views, analytics.

- src/bau/publishing.py
  - Publishing and platform output abstraction.

- src/bau/opportunity.py
  - Opportunity identification and evaluation.

- src/bau/economics.py
  - Cost and business analysis components.

- src/bau/accounting.py
  - Accounting and financial data handling.

These form domain-specific business capabilities that can be invoked by the same actor/controller structure rather than being reimplemented as a new framework.

6. Discovery, research, and repo intelligence

- src/bau/scout/
  - Repo and tool intelligence layer.

- src/bau/toolbox.py
  - Large tool catalog and open-source evaluation structure.

- docs/engineering/repo-intelligence.md
  - Engineering documentation for repo-scouting and evidence-based integration.

This is a strong existing foundation for the future Jarvis discovery engine. The universal capability discovery system should expand these capabilities rather than replace them.

7. UI and desktop experience

- src/bau/ui/
  - User interface, Mission Control, and Jarvis-facing dashboard.

- assets/
  - Visual assets and status/interface presentation.

These are not the core of the orchestrator; they are the presentation and interaction layer.

8. Installation, lifecycle, local system deployment

- installer/
  - Installation and payload creation.

- image/
  - Debian/live ISO generation.

- vm/
  - Virtual machine rehearsal.

- docker/
  - Dockerized local test drive.

These are operational deployment layers and should remain separate from the executive orchestration logic.

9. Existing verification and CI

- pytest suite under tests/
- pyproject.toml defines dependency and test configuration.
- .github/workflows/ci.yml runs lint, secret scan, policy validation, shellcheck, and pytest.

This is the canonical verification layer to preserve and extend.

Architecture-level conclusions

The repository already contains a coherent operating system-like control plane. It is not a blank slate or a generic chatbot app.

What already exists

- Task lifecycle and recovery: src/bau/jobs.py
- Capability validation and registry: src/bau/registry.py
- Model/tool and capability abstraction: src/bau/models and src/bau/toolbox.py
- Governance and sandbox controls: governor, sandbox, policy, regulations, network, security modules
- User-facing orchestrator: assistant / jarvis / team / supervisor
- Repo intelligence and discovery: scout / toolbox / engineering docs
- Deployment lifecycle: installer, image, docker, vm
- CI verification: pytest + GitHub Actions

What is still missing or partial

- A single, small executive controller interface that can coordinate tasks explicitly without duplicating JobStore or registry logic
- A generic adapter contract that can represent model providers, coding agents, browser tools, execution environments, and MCP capability providers
- An explicit mapper between existing registry logic and future capability discovery / model routing
- A clear process for adding capability adapters without hard-coding to one framework or one model vendor

The correct integration strategy

We should not build a second controller, second registry, or second job queue.

We should instead:

1. Extend the existing registry and lifecycle model.
2. Add a thin, explicit adapter contract for future integrations.
3. Add a minimal executive controller that depends on the existing structure.
4. Keep the governance, approval, and sandbox layers authoritative.
5. Let the future full Jarvis architecture grow as adapters and models rather than competing monolithic implementations.

This physically preserves the work already in the repo and keeps the system coherent as it expands toward the universal Jarvis operating environment.
