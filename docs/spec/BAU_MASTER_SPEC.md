# BAU/BSA MASTER BUILD SPEC (v1.0)

**Autonomous AI Business Computer: Compliance-First Production Architecture**

Status: FINAL MASTER ENGINEERING SPECIFICATION (v1.0). Amendments v1.1 are in `docs/SPEC_GAP_ANALYSIS.md` Part D; where they conflict with this document, v1.1 governs.

Mission: build one dedicated AI-native business computer that can operate continuously as a secure, auditable, revenue-producing BAU/BSA autonomous business platform.

Critical caveat: no software can truthfully guarantee "no lawsuit" or universal legal compliance. The system is designed to:
- detect applicability;
- enforce controls;
- preserve evidence;
- block ambiguous or high-risk operations;
- escalate legal questions to qualified human counsel, rather than pretending an AI can replace a lawyer or CPA.

Compliance cannot be a document sitting beside the application. Before the system collects data, generates content, makes a recommendation, sells something, bills somebody, publishes something, uses somebody's likeness, or deploys an AI agent, it must determine what rules apply and produce the evidence that it complied.

---

## 0. The non-negotiable mission

This system is a production business computer: not an experiment, chatbot collection, vibe-coding environment, or pile of disconnected repositories.

The finished machine must be able to:
- understand the history of the BAU/BSA project and remember why decisions were made;
- discover and evaluate new technology, and safely integrate open-source repositories;
- run local and cloud AI models, and route work between models and agents;
- operate tools through controlled permissions;
- create software and media;
- research markets, and create businesses and digital products;
- automate business operations and manage customer workflows;
- produce revenue and track costs;
- track IP, ownership and royalties, taxes and potential tax nexus;
- maintain legal/compliance evidence, and disclose AI involvement where required;
- provide accessible interfaces, and permit easy cancellation and account/data-rights workflows;
- maintain security and provenance;
- survive reboot/failure and recover interrupted jobs;
- continuously monitor regulatory changes;
- remain under human control.

Central principle: **BAU/BSA owns the control plane. Everything else is a replaceable capability.** Operating systems, models, agents, MCP servers, repositories, cloud providers, media engines, APIs and external services are workers. None of them becomes the master authority.

## 1. Core constitution

**1.1 Intelligence does not equal authority.** Authority comes from identity, provenance, permissions, isolation, policy, evidence, validation, observed behavior and explicit authorization.

**1.2 External content is untrusted.** Data, not instructions:
- webpages, PDFs, emails;
- GitHub repositories and documentation;
- social media;
- MCP responses, API responses and tool outputs;
- downloaded files and customer uploads;
- model outputs and generated code;
- third-party prompts.

No external document may redefine system policy.

**1.3 Open source is not automatically trusted.** Every external repository moves through these states in order: DISCOVERED → UNTRUSTED → SENTINEL SCAN → LICENSE REVIEW → PROVENANCE REVIEW → DEPENDENCY/SBOM REVIEW → SECURITY REVIEW → QUARANTINE → SANDBOX → TEST → BENCHMARK → COMPLIANCE REVIEW → REGISTERED → APPROVED → ACTIVE.

**1.4 No secret belongs in source code.** These never appear in source code, Markdown specifications, Git history, screenshots, logs or model prompts:
- API keys and private tokens;
- passwords and recovery codes;
- private certificates and signing keys;
- customer credentials;
- banking credentials.

Use a controlled secret store/environment mechanism.

**1.5 Every important action produces evidence.** Record: WHO, WHAT, WHY, WHEN, WITH WHICH MODEL, WITH WHICH VERSION, USING WHICH DATA, USING WHICH TOOL, UNDER WHICH POLICY, UNDER WHICH JURISDICTION, WITH WHICH PERMISSION, WITH WHICH APPROVAL, WHAT RESULT, WHAT EVIDENCE, WHAT COST, WHAT CHANGED.

## 2. System layers

From the bottom up:
1. Physical laptop
2. BIOS / UEFI / hardware
3. AI-native Linux
4. Host security / trust plane
5. BAU control plane
6. BAU Executive / Jarvis
7. Universal gateway
8. Capability graph
9. Model router
10. Agent router
11. MCP / tool router
12. Local + cloud models
13. Knowledge / memory
14. Project Genesis
15. Media / spatial / software / business factories
16. Compliance / IP / tax / economics
17. Mission Control

Security, compliance, provenance, observability and recovery operate across every layer.

## 3. Operating system foundation

**3.1** Selected foundation: MohaMehrzad/aiOS. It provides:
- AI-native Linux built on Rust, Python, llama.cpp and gRPC;
- AI runtime, tool runtime, memory and API gateway;
- management console;
- rootless Podman, AppArmor and capability-based permissions;
- audit trail, rollback and spending controls.

**3.2 Commercial license gate.** The current aiOS repository uses a noncommercial PolyForm license, so: DO NOT deploy the commercial revenue-producing system until commercial licensing is resolved.
- The installer must record: OS_LICENSE_STATUS, OS_LICENSE_VERSION, OS_COMMERCIAL_RIGHTS, OS_LICENSE_SOURCE, OS_LICENSE_LAST_VERIFIED, OS_LICENSE_APPROVAL.
- If the license is unsuitable: BLOCK COMMERCIAL DEPLOYMENT.
- The architecture must permit replacing the OS foundation without rebuilding the BAU control plane.

*(v1.1 D-1: Debian stable is the base OS; aiOS is optional behind this gate.)*

## 4. Pre-wipe hardware gate

Do not wipe the laptop immediately. First run a read-only audit collecting:
- CPU, RAM, GPU, iGPU, NPU, VRAM;
- NVMe/SATA, total storage, free storage, partitions, filesystems, external storage;
- network, Wi-Fi, Bluetooth;
- camera, microphone, audio, display;
- UEFI/BIOS, Secure Boot, TPM, IOMMU, virtualization;
- battery, thermals;
- current OS.

Create BAU-HARDWARE-BASELINE, BAU-DISK-BASELINE, BAU-SYSTEM-BASELINE, BAU-NETWORK-BASELINE and BAU-BACKUP-BASELINE.

**4.1 Backup gate.** Before destruction, back up:
- source code, repositories, project documents and research;
- media, music, generated artifacts;
- automation definitions, model inventory, configuration;
- SSH/Git configuration, licenses;
- business records, genealogy/research material;
- historical AI conversations;
- environment-variable names;
- deployment documentation.

Never export secret values into the documentation archive.

## 5. Destructive wipe gate

The system must not wipe itself merely because a previous plan authorized a wipe. Immediately before destructive operations it must display:
- TARGET DEVICE, DEVICE IDENTIFIER, STORAGE CAPACITY;
- BACKUP VERIFIED, RECOVERY VERIFIED;
- OS LICENSE VERIFIED;
- K3 DEPLOYMENT MODE;
- GOLDEN RECOVERY PLAN.

Then require fresh human confirmation.

## 6. K3 local intelligence floor

K3/Kimi K3 is a local intelligence reserve for:
- offline and private reasoning;
- diagnostics, planning and system recovery;
- degraded mode and cloud-outage fallback;
- historical analysis and local document processing.

It is not automatically the fastest everyday model, and hardware reality must be measured. If the local machine cannot economically hold it: REGISTER AS OFFLOAD / REMOTE / EMERGENCY CAPABILITY. Never fake local availability.

## 7. BAU Executive / Jarvis

The top-level controller (codename JARVIS) receives objectives and coordinates the system. In order, it must:
1. understand the objective;
2. load historical context;
3. determine jurisdiction;
4. identify applicable laws/policies;
5. classify risk;
6. classify data;
7. inspect IP/provenance;
8. calculate blast radius;
9. build a mission plan;
10. select agents;
11. select models;
12. select tools;
13. verify permissions;
14. obtain approvals;
15. execute;
16. verify;
17. record evidence;
18. calculate economics;
19. update memory;
20. checkpoint;
21. recover if necessary;
22. determine next action.

Jarvis is NOT unrestricted root access. It cannot bypass security policy, permissions, compliance gates, approval requirements, financial controls, IP controls, data rights or tax controls.

## 8. Standard execution pipeline

OBJECTIVE → CONTEXT → JURISDICTION → RISK CLASSIFICATION → DATA CLASSIFICATION → IP/PROVENANCE → LICENSE → PRIVACY → AI REGULATION → CONSUMER PROTECTION → ACCESSIBILITY → SECURITY → SUPPLY CHAIN → HUMAN REVIEW REQUIREMENT → PLAN → AUTHORIZATION → EXECUTION → VERIFICATION → EVIDENCE PACKAGE → PUBLICATION/PAYMENT/DEPLOYMENT GATE → RECORD RETENTION → MONITORING → LEARNING.

## 9. Compliance engine

A first-class subsystem (`/bau/compliance/`). Never a static "BAU is compliant". Instead: "For this transaction, this customer, this product, this jurisdiction, this data type, this AI system, and this date, these requirements apply."

## 10. Regulatory intelligence engine

**Continuously monitor:**
- federal, state, local and international laws;
- regulations, regulatory guidance and enforcement actions;
- materially relevant court decisions;
- standards;
- platform policies, marketplace requirements, payment-provider rules, app-store rules and advertising rules;
- AI-model licenses, open-source licenses and data licenses.

**Prioritize authoritative sources:**
- US federal: FTC, FCC, FDA, SEC, IRS, USPTO, U.S. Copyright Office, DOJ, NIST, CISA, EEOC, HHS, COPPA/FTC;
- US state: state attorneys general, state privacy authorities, CPPA;
- EU: European Commission, EDPB, EU AI Office, EUR-Lex;
- accessibility authorities;
- platform policy sources.

## 11. Regulation registry

Every rule becomes a machine-readable record with these fields:
- **Identity:** reg_id, jurisdiction, authority, law, regulation, section, version.
- **Status and dates:** status, proposal_or_final, effective_date, enforcement_date.
- **Scope:** applicability, covered_entities, covered_products, covered_data, risk_class.
- **Requirements:** obligations, prohibited_actions, required_disclosures, required_consents, consumer_rights, cancellation_requirements, retention_requirements, security_requirements, accessibility_requirements, AI_disclosure_requirements, recordkeeping_requirements.
- **Consequences:** penalties, exceptions, evidence_required.
- **Maintenance:** source_url, last_verified, next_review, review_frequency, owner, legal_review_required.

*(v1.1 C-04: `status` splits into `legal_status` and `bau_status`.)*

## 12. The system must not claim universal compliance

UNKNOWN ≠ COMPLIANT.

| Situation | Status | Action |
|---|---|---|
| Cannot determine whether a regulation applies | UNKNOWN | ESCALATE |
| Two rules conflict | CONFLICT | HUMAN LEGAL REVIEW |
| Applicability depends on missing facts | INCOMPLETE_FACTS | REQUEST INFORMATION |

## 13. AI regulation layer

Track at minimum:
- EU AI Act and GPAI obligations;
- AI transparency, AI-generated-content disclosure, deepfake requirements and synthetic media;
- biometric systems and emotion recognition;
- automated decision-making, high-risk AI and prohibited AI practices;
- human oversight, technical documentation, incident reporting, cybersecurity and model evaluation;
- copyright/training-data obligations;
- US federal AI requirements, state AI laws and sector-specific AI regulation.

EU AI Act Art. 50 transparency applies from 2026-08-02. BAU therefore needs a universal AI CONTENT DISCLOSURE SERVICE.

## 14. AI-generated content disclosure

Every generated artifact receives metadata:
- **Authorship flags:** ai_generated, ai_assisted, human_authored, human_modified.
- **Generation:** model, model_id, provider, generation_timestamp, generation_job, source_material.
- **Media flags:** synthetic_media, deepfake, likeness_used, voice_clone, consent_status.
- **Disclosure:** disclosure_required, disclosure_text, machine_readable_marking, provenance_record.

Where legally required, disclose clearly and visibly at the point of exposure. Examples: AI-GENERATED, AI-ASSISTED, SYNTHETIC MEDIA, AI-GENERATED VOICE/IMAGE/VIDEO, AI-ALTERED CONTENT. Exact wording is determined by the applicable rule, product and context.

## 15. Human authorship / copyright

Track:
- human contribution and AI contribution;
- prompt and source material;
- selection, arrangement, editing, modification and transformation;
- final human creative decisions;
- model and model license;
- third-party assets;
- training/data provenance where available.

Never automatically claim "this AI-generated work is copyrighted". Determine and record what human authorship exists.

## 16. Synthetic likeness / voice / identity

Before generating or publishing a person's identity, face, likeness, voice, name, signature, persona or digital replica, determine:
- identity and consent;
- authority and license;
- purpose, territory and term;
- revocation and compensation;
- platform and publication rights.

No consent, ambiguous consent, or an expired license: BLOCK.

## 17. Data governance engine

**Per data object:**
- **Identity:** data_id, source, owner, subject, category, sensitivity.
- **Legal basis:** purpose, lawful_basis, consent, collection_date.
- **Storage:** retention_period, location, processors, subprocessors, transfer_locations, encryption.
- **Policies:** access_policy, deletion_policy, export_policy, correction_policy, consent_revocation.
- **Use:** automated_decision_use, model_training_use, sharing_status.

**Classes:** PUBLIC, INTERNAL, CONFIDENTIAL, PERSONAL, SENSITIVE_PERSONAL, FINANCIAL, AUTHENTICATION, HEALTH, CHILD/MINOR, BIOMETRIC, LEGAL, TRADE_SECRET, CRITICAL.

## 18. Data minimization

Do we actually need this data? If not, do not collect it. If collected temporarily, delete it when the purpose ends. Never retain data merely because storage is cheap.

## 19. User data rights engine

**Workflows, where applicable:**
- access, correction, deletion, portability;
- restriction, objection, opt-out, consent withdrawal, marketing opt-out;
- automated-decision-making rights, profiling opt-out;
- appeal, complaint, data export.

**Each request records:** request_id, identity_verification, jurisdiction, rights_invoked, received_at, deadline, systems_searched, data_found, actions_taken, exceptions, response, completion_timestamp, evidence.

## 20. Deletion must actually propagate

Evaluate every store:
- primary database, backups, object storage;
- search indexes, vector database, cache;
- memory, agent memory, model context;
- logs, analytics, exports;
- customer workspaces, third-party processors.

Where deletion is legally required and possible, execute and record it. Where retention is legally required: RETAIN, DOCUMENT THE LEGAL BASIS, RESTRICT USE.

## 21. Consent engine

**Never use:**
- hidden consent;
- preselected consent where prohibited;
- bundled unrelated consent;
- deceptive buttons or confusing language;
- fake urgency or other dark patterns.

**Consent records:** what, why, when, version, language, interface, user action, IP/session evidence where legally appropriate, withdrawal mechanism.

## 22. Cancellation engine

Every recurring product needs a dedicated cancellation path. It must never be intentionally harder than enrollment where law requires equivalent simplicity.

**Subscribe:** SUBSCRIBE → CLEAR PRICE → BILLING FREQUENCY → TRIAL END DATE → RENEWAL TERMS → CANCELLATION METHOD → CONSENT → RECEIPT.

**Cancel:** OPEN → AUTHENTICATE → CANCEL → CONFIRM → STOP FUTURE RECURRING CHARGES → RECEIPT → RECORD.

**Never:**
- call-us-only or email-us-only cancellation;
- hidden settings;
- endless retention screens;
- fake errors or broken buttons;
- unnecessary questionnaires.

The system must independently test its own cancellation path. *(v1.1 C-09: the legal basis is ROSCA, FTC Act s.5 and state ARLs; the 2024 FTC rule was vacated.)*

## 23. Subscription compliance test

Before a subscription goes live, every item must hold:
- price visible;
- billing frequency visible;
- renewal visible;
- trial conditions visible;
- material limitations visible;
- cancellation visible;
- consent captured, and its evidence retained;
- cancellation tested, with a confirmation generated;
- recurring billing stops correctly;
- refund policy visible;
- contact method visible;
- terms accessible;
- privacy policy accessible;
- accessibility, mobile and keyboard tested.

## 24. Consumer protection engine

Every marketing claim goes: CLAIM → EVIDENCE → SUBSTANTIATION → JURISDICTION → DISCLOSURE → APPROVAL.

Never permit these unsubstantiated claims:
- "guaranteed", "risk-free", "never fails";
- "fully autonomous", "100% accurate", "human-level";
- "completely secure", "fully compliant", "legally protected";
- "copyright guaranteed", "tax guaranteed";
- "FDA approved".

## 25. AI marketing claims

Maintain an AI_CAPABILITY_CLAIMS_REGISTRY. Each entry records: claim, evidence, test, date, model/version, scope, limitations, reviewer, expiration. Expired evidence makes the claim STALE, and marketing is blocked until it is reviewed.

## 26. Privacy / cookie / tracking engine

Before tracking, answer:
- What is collected, why, where, and for how long?
- Who receives it?
- Is consent or opt-out required?
- Can it be disabled or deleted?

Registries: COOKIE, TRACKING, ANALYTICS, AD_TECH, PIXEL, THIRD_PARTY_SDK.

## 27. Children / minors

Anything that may involve minors triggers MINOR_DATA_POLICY. Review:
- age requirements and parental consent;
- data minimization;
- profiling, advertising and behavioral tracking;
- AI interaction and content;
- retention, deletion and safety;
- applicable child-protection laws.

If age applicability cannot be determined, ESCALATE.

## 28. Accessibility engine

Everything must be usable by keyboard, mouse, touch, screen reader, low vision, reduced motion, high contrast and scaling.

Minimum requirements:
- visible focus, logical tab order, no keyboard traps, skip links;
- semantic labels;
- accessible forms, errors, tables, dialogs and notifications;
- captions and transcripts;
- sufficient contrast, scalable text, reduced motion;
- no drag-only interaction and no mouse-only operation.

Target WCAG 2.2 AA, while tracking each jurisdiction's legal standard.

## 29. Keyboard-first requirement

Every critical operation has a GUI, a CLI, a command palette and a keyboard shortcut. Critical actions cannot require a mouse. Shortcut registry fields: command, default_key, conflicts, remappable, danger_level, confirmation_required.

## 30. Accessibility acceptance test

Every release must pass:
- tab through everything, and Shift+Tab through everything;
- Enter everything, and Escape everything;
- arrow through menus;
- screen reader test;
- zoom, high-contrast and reduced-motion tests;
- mobile test.

## 31. California / state privacy engine

Build a generalized JURISDICTIONAL_PRIVACY_ENGINE, not a California-only one. It tracks per state:
- threshold, consumer definition, business definition, data definition;
- rights, opt-outs and consent;
- ADMT, risk assessment, cybersecurity, auditing;
- deletion, appeal, retention;
- effective dates.

## 32. Automated decision-making

Any consequential decision about a person triggers ADMT_REVIEW. Determine:
- decision type and legal significance;
- data used and model;
- explanation, human review, appeal and opt-out;
- auditability and discrimination/bias risk;
- jurisdiction.

## 33. High-impact AI actions

Stronger controls apply to: employment, housing, lending, insurance, education, healthcare, legal decisions, government eligibility, financial transactions, identity, biometric decisions, children, and safety-critical actions. Default: HUMAN REVIEW REQUIRED.

## 34. AI safety / NIST layer

NIST AI RMF (GOVERN, MAP, MEASURE, MANAGE) is the baseline. Every important AI system documents its purpose, risk, limitations, evaluation, monitoring, incident process, human oversight and documentation.

## 35. Incident management

**Classes:**
- security, privacy, data loss;
- AI safety, AI misuse, model failure;
- IP, copyright, licensing;
- consumer, financial, tax, regulatory;
- accessibility, content, reputational.

**Lifecycle:** DETECT → CONTAIN → CLASSIFY → PRESERVE EVIDENCE → NOTIFY → REMEDIATE → VERIFY → DOCUMENT → LEARN.

Never delete evidence after an incident.

## 36. Supply-chain security

Per repository, record:
- **Source:** repository, owner, commit, release, artifact hash, license.
- **Build:** dependencies, SBOM, build process, signatures, provenance.
- **Risk:** security findings, known vulnerabilities, install scripts.
- **Observed behavior:** network, filesystem, process, persistence, telemetry.
- **Exposed surfaces:** MCP surfaces, agent surfaces.

## 37. MAYA Sentinel

The mandatory intake gate: DISCOVER → SENTINEL → LICENSE → STATIC ANALYSIS → PROVENANCE → SANDBOX. Never git clone → pip/npm install → execute from an untrusted repository.

## 38-41. Project Genesis: historical intelligence

The entire historical AI-conversation corpus becomes an engineering asset.
- **Tools:** open-context is the primary ingestion layer; chat-history-importer and chat-history-index-mcp are companions.
- **Reconstruct:** what was requested, built, rejected or corrected; why things were chosen and what they replaced; what remains unfinished; dependencies; what is obsolete; security, license and business gaps.
- **Pipeline:** RAW EXPORTS → OPEN-CONTEXT → NORMALIZATION → DEDUPLICATION → RAW CORPUS → HISTORICAL ANALYSIS → CONTRADICTION DETECTION → DECISION / REQUIREMENT / CORRECTION EXTRACTION → DEPENDENCY GRAPH → GAP ANALYSIS → HUMAN REVIEW → CANONICAL BAU KNOWLEDGE → MAYA MEMORY LANE → CAPABILITY GRAPH.
- **Status tags:** PAST, CURRENT, PLANNED, EXPERIMENTAL, REJECTED, DEPRECATED, UNKNOWN.
- **Canonical documents:** BAU_ + PROJECT_MASTER, DECISIONS, CORRECTIONS, REQUIREMENTS, ARCHITECTURE, CAPABILITY_GRAPH, SECURITY_MODEL, BUSINESS_FACTORIES, MODEL_REGISTRY, REPOSITORY_REGISTRY, COMPLIANCE_MATRIX, REGULATORY_REGISTER, IP_PROVENANCE, TAX_NEXUS, DATA_GOVERNANCE, AI_DISCLOSURE, ACCESSIBILITY, CONSUMER_RIGHTS, OPEN_QUESTIONS, DEPRECATED_IDEAS, BUILD_STATE, INCIDENT_REGISTER (each `.md`).

## 42. MAYA Memory Lane

Persistent local-first memory built on Markdown, JSON, SHA-256-linked records, searchable memory, resume phrases, deterministic export and chain verification. Tools: ml_search, ml_answer, ml_recent, ml_resume. Memory is not authority; canonical BAU state remains in `.bau/`.

## 43-47. Capability graph and models

**Capabilities:** provider, model, agent, MCP, repository, API, dataset, factory, connector, service.

**Relations:** DEPENDS_ON, REQUIRES, PROVIDES, REPLACES, CONFLICTS_WITH, FALLBACK_FOR, LICENSED_BY, OWNED_BY, USES_DATA_FROM, GENERATES, PUBLISHES_TO.

**Model registry fields:**
- **Identity:** model_id, name, version, provider, source, repository, commit.
- **Licensing:** license, commercial_use.
- **Deployment:** local/cloud, hardware, dependencies.
- **Capability:** capabilities, context, input/output types.
- **Operations:** cost, latency, privacy, health, benchmark, limitations, status, replacement candidates.

**Router inputs:** task, quality, latency, cost, privacy, context, hardware, license, tool support, multimodal support, availability, risk. Never use an expensive model for deterministic work.

**Trust levels:** OFFICIAL, VERIFIED, QUANTIZED, MERGED, MODIFIED, ABLITERATED, THIRD_PARTY, UNKNOWN. Unverified models stay isolated.

**Heretic Model Transformation Lab:**
- never overwrite the original model;
- record parent_model/hash, tool_version, configuration, timestamp, derived_hash, benchmark, behavior_profile and license;
- it can alter model behavior, but cannot increase system authority.

## 48-55. Agents, permissions, gateway, MCP, network, endpoints, blast radius, revocation

**Agent records:** agent_id, version, purpose, model, fallback, workspace, memory_scope, permissions, budget, network_scope, tools, approval_policy, audit_policy, risk_level, status.

**Agent classes:** EXECUTIVE, ARCHITECT, CODER, QA, RESEARCH, BROWSER, COMPUTER_USE, MEDIA, VIDEO, MUSIC, BUSINESS, SALES, MARKETING, SUPPORT, DATA, FINANCE, DEVOPS, SECURITY, DOCUMENTATION, PUBLISHING, OPPORTUNITY_MINER.

**Permission levels:** READ_ONLY, LOW_RISK, REVERSIBLE, APPROVAL_REQUIRED, HIGH_IMPACT, CRITICAL. Examples:

| Capability | Level |
|---|---|
| github.read | READ_ONLY |
| github.write | APPROVAL_REQUIRED |
| publish.video | APPROVAL_REQUIRED |
| delete.customer.data | HIGH_IMPACT |
| move.money | CRITICAL |
| change.tax_configuration | CRITICAL |

**Universal gateway verbs:** discover, search, inspect, status, run, build, test, browser, files, project, workflow, artifact, checkpoint, resume, verify, revoke. No hidden agent-to-agent execution paths.

**MCP registry:** identity, version, source, license, tools, permissions, network, data access, credentials, risk, sandbox, provenance, health, last verified. MCP tools are capabilities, not trusted administrators.

**Network trust states:** OFFLINE, UNKNOWN, UNTRUSTED, LIMITED, TRUSTED, VERIFIED. Coffee-shop Wi-Fi is UNTRUSTED, which automatically means:
- require TLS and validate certificates;
- disable unnecessary inbound services;
- minimize credentials and restrict sensitive calls;
- increase verification;
- limit administrative operations.

**Endpoint trust registry:** service, domain, expected_identity, tls_policy, ca_policy, public_key_pin, backup_pin, rotation_policy, last_verified. Pin selectively; never blindly.

**Blast radius:** LOW, MEDIUM, HIGH or CRITICAL, scored on data affected, systems affected, financial impact, external visibility, irreversibility, credentials, customer impact and legal impact.

**Revocation:** capabilities are independently revocable (e.g. github.write OFF while github.read stays ON) without rebuilding the system.

## 56-59. Media, music video, spatial

- **Open-Generative-AI** (Anil-matcha) is the media implementation layer: image, video, cinema, audio, motion, clipping, design, workflows, agents. It is not the master controller and must pass Sentinel.
- **Media gateway verbs:** generate_image/video/audio/music/voice, lip_sync, create_scene/storyboard/character/clip, upscale, caption, render. Adapters: LOCAL, OPEN-SOURCE, CLOUD-A, CLOUD-B, FUTURE.
- **Music video factory:** the actual audio is the master timing source. Analyze waveform, beat grid, tempo, bass hits, pauses, drops, vocals, energy, arrangement, lyrics, sections and transitions.
- **God's Eye (spatial intelligence):**
  - **Verbs:** spatial.world_view / aircraft / vessels / satellites / events / public_cameras / create_scene / export_scene.
  - **Data:** authorized and public data only.
  - **Prohibited:** no covert private-person surveillance or stalking.

## 60-65. Business factories

Factories are modular and are not all activated at once. Initial factories: Faceless Media, Digital Assets, Books, Music/Entertainment, Automation Services, God's Eye Media.

**Opportunity Miner:**
- **Inputs:** public datasets, business info, open source, tech releases, market info, industry changes, public procurement, government opportunities, media trends, local business categories.
- **Outputs:** opportunity, evidence, value, competition, capability, startup cost, time, risk, automation potential, recommended action.
- **Decisions:** CONTINUE / IMPROVE / AUTOMATE / PAUSE / KILL.

**Faceless media pipeline:** niche → audience → opportunity → topic → research → fact check → script → editorial QA → storyboard → voice → visuals → music → edit → thumbnail → title → description → AI disclosure → accessibility → rights check → final QA → approval → publish → analytics → learning.

**Book factory:** market → topic → audience → research → outline → chapters → fact check → editorial → consistency → cover → rights → format → accessibility → proof → distribution → analytics.

**Digital assets:**
- **Examples:** templates, planners, business kits, graphics, music, sound packs, videos, educational products, automation templates, developer utilities, prompt systems, creative packs.
- **Each asset requires:** provenance, license, ownership, AI status, human contribution, commercial rights and platform rights.

**Automation services:** opportunity → discovery → qualification → process map → design → security → privacy → compliance → prototype → QA → customer approval → deployment → monitoring → maintenance.

## 66-73. IP, royalties, tax, accounting, money

**IP ledger (per IP_ASSET_ID):**
- **Parties:** creator, contributors, owner, ownership_percent.
- **Rights:** license, commercial_rights, territory, exclusivity, term, consent.
- **Origin:** source_assets, model, provider, inputs, training_data_information, third_party_material, provenance.
- **Money:** royalty, revenue_share, commission, platform.

**Royalty engine:** gross revenue, platform fee, payment fee, affiliate fee, royalty, co-owner share, creator share, tax withholding, net revenue, BAU share. No payment while ownership is unresolved.

**Tax engine (`/bau/tax/`):**
- **Where:** entity, state, country, customer location, transaction location, sales channel.
- **What:** product/service type, digital/physical goods, gross receipts, taxability, exemption, marketplace facilitator.
- **Taxes:** sales/use tax, income, royalty, withholding.
- **Paperwork:** 1099, W-9, W-8, invoice, receipt, payment, filing obligation.
- **Nexus status:** computed as POTENTIAL, CONFIRMED, NO CURRENT or UNKNOWN. Never "BAU doesn't owe this tax" without verified law and facts.

**Tax rule versioning:** every rule records jurisdiction, rule, threshold, effective date, expiration date, source, last verified and next review. Never hard-coded.

**Royalty tax records:** payer, payee, amount, date, IP asset, agreement, tax form status, withholding, payment method, supporting documentation.

**Accounting evidence:**
- **Documents:** invoice, receipt, contract, order.
- **Money flows:** payment, refund, tax, commission, royalty, expense.
- **Context:** vendor, customer, date, currency, supporting evidence.

**Money movement:** READ → PREPARE → RECOMMEND → REQUEST_APPROVAL → EXECUTE. High-value execution requires human approval.

## 74-75. Compliance policy compiler and gate states

Regulations compile into machine-checkable policies, for example:
- subscription + jurisdiction → require price, frequency and renewal disclosure, informed consent, a cancellation path and a cancellation test; retain evidence;
- synthetic content with disclosure required → block publication until a machine-readable marking and a visible disclosure exist;
- IP owner UNKNOWN → block monetization.

**Gate states:** PASS, PASS_WITH_REVIEW, BLOCKED, UNKNOWN, EXPIRED, CONFLICT. Only PASS, or PASS_WITH_REVIEW plus human approval, may proceed. *(v1.1 C-02 adds INCOMPLETE_FACTS and NOT_APPLICABLE.)*

## 76-83. Legal pages, visibility, terms, testing, platforms, content rights, data rights, providers

- **Legal page generator:**
  - **Pages:** ToS, privacy, cookies, AI disclosure, refund, cancellation, acceptable use, licensing, IP notice, DMCA, accessibility statement, contact, data-rights process, subprocessors, security disclosure.
  - **Versioning:** each page records version, effective_date, jurisdiction, legal_basis, last_review and next_review.
  - **Prohibited:** no stale boilerplate.
- **Front-line visibility:** if AI generates, transforms, assists, interacts, recommends, impersonates, synthesizes or makes a consequential decision, decide whether disclosure is required and, if so, disclose prominently. Never hide it in footers, buried terms, tiny type, help pages, source code or metadata only. Where machine-readable disclosure is required, provide both.
- **Terms versioning:** old version, new version, change summary, effective date, user notification, consent required? Never silently replace material terms.
- **Periodic regression:** SIGNUP → BILL → CANCEL → STOP BILLING → DELETE REQUEST → DATA EXPORT. If cancellation breaks: ALERT, DISABLE NEW SALES if material, FIX, RETEST.
- **Platform policy records:** platform, policy_version, AI-content, copyright, music, advertising, commercial-content, API and automation policies, account limits, appeal process, last_verified.
- **Content rights before publishing:** music, image, video, voice, font, stock, model license, data license, character, trademark, likeness, location, archival material. Anything unresolved: BLOCK OR ESCALATE.
- **Data/AI training rights** are distinct: viewed / stored / processed / indexed / embedded / inference / training / shared / commercialized.
- **Provider boundary:** data sent, data retained, training policy, privacy policy, jurisdiction, commercial rights, model license, API terms, subprocessors, security, cost. Never send sensitive data to a provider merely because it gives better results.

## 84-89. Economics, usage, jobs, checkpointing, reboot, offline

**Costs tracked:**
- AI: model, API, GPU, CPU;
- infrastructure: storage, network, tool;
- people and distribution: human time, distribution;
- money flows: payment fees, royalties, taxes;
- failure cost.

**Metrics:** revenue, gross margin, net margin, profit per hour, AI cost/revenue, automation %, failure rate, CAC, LTV.

**MAYA usage dashboard:** provider balance, spend, burn rate, runway, health, stale keys, rejected keys, authentication failures, rotation reminders. Never expose secret values.

**Job record:**
- **Identity:** job_id, mission_id, objective, agent, model, tools.
- **I/O:** inputs, outputs, artifacts.
- **Resources:** cost, duration.
- **Control:** permissions, risk, approvals, evidence.
- **State:** status, errors, retries, rollback_state, compliance_status.

**Checkpoint:** objective, state, completed/remaining steps, artifacts, permissions, approvals, model, tool state, memory references, cost, errors, next action.

**Reboot:** VERIFY SYSTEM → CAPABILITIES → AUDIT → MEMORY → REGISTRY → CREDENTIAL AVAILABILITY → RESTORE JOBS → RESTORE CHECKPOINTS → REVALIDATE AUTH → RESUME. No important mission disappears because of a reboot.

**Offline mode:** use local model, local memory, local documents, deterministic tools, local code and local audit. Network-dependent jobs become WAITING_FOR_NETWORK.

## 90-91. Golden baseline and repository structure

**Golden baseline:** freeze versions, record hashes, capture manifest, back up config/registries/memory/compliance/security, create recovery image, create acceptance suite.

**Updates:** TEST → CANARY → VALIDATE → PROMOTE, or ROLLBACK. No uncontrolled auto-update of critical components.

**Repository structure:**
- `/bau/.bau/{config, policies, schemas, registry, memory, history, compliance, regulations, ip, tax, data, security, audit, evidence, jobs, checkpoints, artifacts, tests, benchmarks, snapshots, reports}`
- `/bau/{core, orchestrator, gateway, agents, models, mcp, knowledge, project-genesis, media, spatial, factories, finance, devops, security, compliance, ui, cli, skills, connectors, sandbox}`

## 92-95. Regulation monitor, lifecycle, impact graph, dashboard

**Regulation watcher:**
- **Watches:** new law, amendment, proposed/final rule, effective date, enforcement date, court decision, regulatory/agency guidance, platform policy, model license change, data license change.
- **On a change:** DISCOVER → VERIFY OFFICIAL SOURCE → CLASSIFY → MAP TO BAU → IMPACT ANALYSIS → UPDATE POLICY → RUN TESTS → FLAG AFFECTED PRODUCTS → HUMAN REVIEW IF REQUIRED.

**Lifecycle:** PROPOSED → VERIFIED → MAPPED → IMPLEMENTED → TESTED → ACTIVE. Proposed rules are never treated as final law.

**Impact graph:** affected products, customers, data, workflows, models, agents, marketing, contracts, payments, tax, IP and disclosures.

**Dashboard colors:**

| Color | Meaning |
|---|---|
| GREEN | compliant/verified *(v1.1: "controls passed")* |
| YELLOW | review required |
| ORANGE | deadline approaching |
| RED | blocked / noncompliant / unknown |
| BLACK | critical security or legal incident |

Never hide red.

## 96-105. Evidence, audit, threats, injection, sandbox, exfiltration, budgets, automation, continuity, backups

**Legal evidence package:**
- **Customer and terms:** customer, terms version, privacy version, consent, disclosure.
- **Status:** AI status, IP status, licenses.
- **Money:** payment, invoice, tax classification, nexus analysis.
- **Provenance:** model, data sources, approvals, logs, output, timestamp.

**Audit chain:** timestamp, event, actor, hash, previous_hash, artifact_hash, policy_version (hash-chained).

**Threat model:**
- network: malicious Wi-Fi, DNS manipulation, MITM, compromised endpoint;
- AI and tooling: malicious MCP, prompt injection, model poisoning, tool abuse;
- software: supply chain, malware, ransomware;
- access: credential theft, privilege escalation, insider threat;
- data: data exfiltration;
- customers: customer abuse, automated fraud.

**Prompt-injection defense:** external content is untrusted data. Authority comes only from BAU policy, user authorization, agent permission and system policy.

**Sandboxing:** rootless containers with filesystem, network, resource and capability restrictions; temporary credentials; ephemeral workspaces.

**Exfiltration control:** before data leaves, ask what data, where, why, who receives it, whether it is allowed, whether consent is required, whether contractual authority exists. Unknown: BLOCK.

**Agent budgets:** per job, hour, day and mission. Exceeded → PAUSE → optimize, change model, or request approval.

**Automation record:** trigger, scope, permissions, budget, frequency, failure policy, rollback, notification, owner, expiration. Nothing runs forever unmonitored.

**Business continuity:**
- backups: local, offline, configuration, documents;
- recovery image;
- exports: historical corpus, memory, registry, compliance;
- financial records.

**Backup test:** RESTORE → VERIFY → BOOT → READ → CHECK HASHES → RUN ACCEPTANCE TEST.

## 106-107. Acceptance suite and critical failures

**Acceptance suite:**
- **System:** boots/reboots, network security, hardware baseline, backup restores, recovery works.
- **History and memory:** AI corpus imported, Project Genesis reconstructed, canonical requirements generated, contradictions identified, memory works.
- **Models and registries:** K3 works or offload registered; model, agent and MCP registries work.
- **Supply chain:** Sentinel works, license gate works.
- **Compliance:** registry works, policy compiler works, AI disclosure works.
- **IP and tax:** IP ledger works, tax/nexus ledger works.
- **Customer workflows:** cancellation works, data-rights workflow works.
- **Accessibility:** passes, including keyboard-only operation.
- **Security and integrity:** security tests pass, audit chain works, checkpoint and resume work, financial controls work.
- **Business:** one factory completes, one real revenue mission completes, evidence package produced.
- **Baseline:** golden baseline created.

**Critical failure conditions** (production-ready may not be declared while any remain):
- critical security issue;
- unknown IP ownership for a commercial asset;
- unknown license;
- unknown high-impact regulatory applicability;
- broken cancellation;
- missing required AI disclosure;
- uncontrolled customer data;
- uncontrolled money movement;
- untested recovery;
- unprotected secrets;
- untrusted executable outside the sandbox;
- broken audit trail;
- missing tax records;
- unresolved high-risk legal issue.

## 108-110. Build phases, first revenue mission, learning loop

**Phases:**

| Phase | Work |
|---|---|
| 0 | Freeze the mission |
| 1 | Hardware audit (read-only) |
| 2 | Backup (complete and verify) |
| 3 | License gates (aiOS, models, repos, media, datasets, APIs) |
| 4 | Wipe/install, only after explicit confirmation |
| 5 | Host hardening |
| 6 | Trust plane |
| 7 | Control plane |
| 8 | Project Genesis |
| 9 | Memory |
| 10 | Model layer |
| 11 | MCP/tool layer |
| 12 | Supply chain |
| 13 | Compliance |
| 14 | IP/tax/economics |
| 15 | Jarvis |
| 16 | Media |
| 17 | Spatial |
| 18 | Business factories (selectively) |
| 19 | Accessibility |
| 20 | Observability |
| 21 | Recovery |
| 22 | Golden baseline |
| 23 | Revenue mission |

**First revenue mission:** pick one factory and run IDEA → CUSTOMER → PRODUCT → CREATION → COMPLIANCE → DELIVERY → PAYMENT → RECORDS → SUPPORT → ANALYTICS. Then improve the platform.

**Learning loop questions:**
- What worked, what failed, what cost too much?
- What could be automated, and what should be removed?
- Which regulation applied, and what was missed?
- What security events occurred, and what customer feedback?
- What generated profit?

Only verified lessons are fed back.

## 111-125. Principles

- **111 No repository hopping:** BAU CONTROL PLANE → CAPABILITY REGISTRY → ADAPTER → EXTERNAL PROJECT. Replace the adapter, never BAU.
- **112 Adapter principle:** Open-Generative-AI → Media Adapter; God's Eye → Spatial Adapter; K3 → Model Adapter → Model Router.
- **113 Compliance is a dependency:** a mission is not READY until its compliance dependencies are RESOLVED. For example, PUBLISH_VIDEO requires AI_DISCLOSURE, IP_CLEARANCE, MUSIC_RIGHTS, PLATFORM_POLICY, ACCESSIBILITY and CONSUMER_POLICY.
- **114 Regulation is data:** REGULATION → STRUCTURED RECORD → POLICY → TEST → EVIDENCE. Never hard-coded into a model's personality.
- **115 Date-aware:** today, rule version, effective date, enforcement date, transition period. Future rules are not yet enforceable; expired rules are not current.
- **116 Jurisdiction-aware:** business, customer, user, data, server, transaction location, market, platform, product.
- **117 Conflict engine:** SEGMENT / RESTRICT / DISCLOSE / OBTAIN CONSENT / DISABLE / HUMAN REVIEW. Never blindly choose the least restrictive jurisdiction.
- **118 Source priority:** statute > final regulation > official agency guidance > official interpretation > court decision > recognized standard > secondary analysis > news > social media. Social posts may discover a change; they never establish the rule.
- **119 Regulatory research agent:**
  1. discover;
  2. locate the authoritative source;
  3. verify it;
  4. capture the exact provision;
  5. capture the effective date;
  6. identify applicability;
  7. map affected capabilities;
  8. propose implementation;
  9. run tests;
  10. request legal review.
- **120 Legal review queue triggers:**
  - new high-risk law, unclear applicability, conflicting jurisdictions;
  - high financial or privacy exposure;
  - IP dispute, significant contract;
  - regulated industry, high-impact AI, digital replica;
  - children, health, finance, employment, government;
  - tax ambiguity.
- **121 Legal posture:** never "you're completely legally protected". Instead: "the system identified these requirements, implemented these controls, collected this evidence, and found these unresolved issues."
- **122 Trust model:** OBSERVE → UNDERSTAND → THREAT MODEL → CLASSIFY → PLAN → AUTHORIZE → EXECUTE → VERIFY → RECORD → LEARN. Never SEE → TRUST → EXECUTE.
- **123 Final principle:** an AI-directed business operating system that discovers, reasons, plans, executes, verifies, documents, accounts for and recovers from work inside explicit security, legal, financial, IP, privacy, accessibility and human-control boundaries.
- **124 Definition of done:** SYSTEM, INTELLIGENCE, HISTORY, MEMORY, SECURITY, COMPLIANCE, IP, TAX, BUSINESS, ACCESSIBILITY, RECOVERY and GOLDEN BASELINE criteria as enumerated in §106-107.
- **125 Final loop:** OBJECTIVE → HISTORICAL CONTEXT → JURISDICTION/LAW → RISK/DATA/IP → SECURITY/LICENSE → PLAN/AUTHORIZE → EXECUTE → VERIFY/QA → DISCLOSE/RECORD → PUBLISH/DELIVER → GET PAID/ACCOUNT → MEASURE/LEARN → NEXT MISSION.

**Production rule:** if BAU cannot explain any of the following, BAU is not finished:
- what it is doing, and why it is allowed to;
- what data it used, and whose property it used;
- what model performed it;
- what law/policy applies;
- what the customer was told;
- what evidence proves compliance;
- what it cost;
- how to undo it.
