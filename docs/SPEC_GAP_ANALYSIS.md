# BAU/BSA Master Spec: Gap and Consistency Review

Reviewed: 2026-10-04, against the Master Build Spec (`docs/spec/BAU_MASTER_SPEC.md`, sections 0-125).
Method: every section was read as an engineer would read a contract. For each section the review asked four questions:

1. Can it be implemented as written?
2. Does it contradict another section?
3. Does it rely on a fact that has changed?
4. Is something a real business needs simply missing?

Status column:
- **FIXED**: resolved in code in this repository.
- **AMENDED**: resolved by the normative amendment in Part D.
- **OPEN**: needs a decision or work that cannot be done from here.

Legal caveat (kept from the spec, §121): this review finds engineering and regulatory-coverage gaps. It is not legal advice. Every regulation record ships as "awaiting counsel sign-off", and the system will not give a clean PASS until a qualified human promotes it.

---

## Part A: Missing entirely (highest risk)

| # | Gap | Why it matters | Status |
|---|-----|----------------|--------|
| G-01 | **No outbound-communications section.** The spec covers subscriptions and privacy but never email, SMS or calls. | The most lawsuit-dense area for a small online business. CAN-SPAM is up to **$53,088 per email**. TCPA is $500-$1,500 **per text** with a private right of action. CASL is up to CAD $10M. PECR (UK) rose to GBP 17.5M / 4% on 2026-02-05. Since Nov 2025, Gmail, Yahoo and Microsoft **reject** non-compliant bulk mail. | **FIXED**: `bau/comms/`, `data/policies/email.yaml`, `sms.yaml`; full runbook in `EMAIL_AND_MESSAGING_COMPLIANCE.md` |
| G-02 | No **FCC wireless-domain** rule (47 CFR 64.3100). | Commercial email to carrier email-to-SMS domains needs express prior authorization. Almost every "email compliance" checklist misses it. | **FIXED**: blocks US sends until the FCC list is loaded and current |
| G-03 | No **fake reviews / testimonials** rule (16 CFR 465, in force 2024-10-21). | The faceless-media and digital-asset factories are exactly where AI-written reviews and bought engagement tempt. Civil penalties apply per violation. | **FIXED**: `pub.no_fake_reviews`, `email.testimonials` |
| G-04 | No **payments / PCI DSS** section. | Spec §72-73 handle accounting, but not card data. PCI DSS v4.0.1 future-dated requirements have been mandatory since 2025-03-31. | **AMENDED** (D-9): never touch card data; hosted checkout only; registry record `pci-dss-4` |
| G-05 | No **breach-notification** rule data. Spec §35 says "NOTIFY" but not whom or by when. | GDPR gives 72 hours. All 50 US states have statutes with differing clocks. | **AMENDED** (D-10): registry record `us-breach-notification`; per-state records OPEN |
| G-06 | No **sanctions / OFAC screening**. | The Opportunity Miner and Automation Service factories take global customers. OFAC liability is strict. | **AMENDED** (D-11); registry record `us-ofac-sanctions`; screening integration OPEN |
| G-07 | No **right-of-publicity** law in the registry. Spec §16 has the right controls but no legal basis to cite. | Voice clones and AI performers are the core of the media factories. CA Civ. Code 3344, NY, and the TN ELVIS Act all apply. | **FIXED**: `us-right-of-publicity`, `pub.likeness_consent` |
| G-08 | No **DMCA designated agent** for any product hosting user uploads. | Without a registered agent (renewed every 3 years) there is no safe harbor. | **AMENDED**; record `us-dmca-512` |
| G-09 | No **European Accessibility Act**. Spec §28 targets WCAG but not the EU law in force since 2025-06-28. | Any e-commerce or e-book sale to EU consumers is in scope (micro-enterprise service exemption aside). | **FIXED** (registry record) |
| G-10 | **Human operator identity and authentication** are undefined. The spec requires "human approval" ~40 times but never says how a human is proven to be human. | Without this, an agent can "approve" its own request. That makes every approval gate decorative. | **FIXED**: each human approver signs with their **own passphrase-protected SSH key** (`ssh-keygen -Y sign`). The agent account can verify against root-owned `/etc/bau/allowed_signers` but holds no signing key. Self-approval and `agent:` approvers are refused, and every approval names the person who gave it. |
| G-11 | No **separation of duties**. | The same identity proposing and approving defeats the control. | **FIXED** (`requester != approver`) |
| G-12 | No **trusted time source**. Spec §115 makes every decision date-aware, but nothing guarantees the clock. | A wrong clock silently applies the wrong law. | **FIXED**: chrony with authenticated NTS servers |
| G-13 | No **full-disk encryption** requirement. Spec §17 has an `encryption` field but the build never encrypts the laptop. | A stolen laptop exposes customer data, which itself triggers breach notification. | **FIXED**: preseed installs LUKS + LVM |
| G-14 | No **retention schedule numbers**. The spec says "retain" without saying for how long. | Too short loses tax/consent evidence. Too long violates minimization (§18). | **OPEN**: needs a CPA plus counsel. Known anchors: IRS generally 3-7 years; CA ARL consent records 3 years; CASL consent proof for as long as you rely on it. |
| G-15 | No **business-formation prerequisites** (entity, EIN, sales-tax permits, business licences, insurance). | Spec §68 tracks nexus but not the registration that must exist before collecting tax. | **OPEN**: checklist in Part D-12 |
| G-16 | Spec §6 relies on **"K3/Kimi K3"** as a local intelligence floor without a known model card, size, or licence. | A trillion-parameter-class MoE model at 4-bit needs hundreds of GB of memory, far beyond any laptop. | **FIXED** in posture: the wipe gate computes K3 mode from measured RAM and defaults to OFFLOAD. The registry refuses a "local" model without a benchmark. |

## Part B: Internal contradictions

| # | Conflict | Resolution | Status |
|---|----------|-----------|--------|
| C-01 | §1.3 and §37 list repository-intake steps in **different orders**. | One canonical state machine (`security/sentinel.py::STATES`); transitions cannot skip steps. | FIXED |
| C-02 | §12 defines `INCOMPLETE_FACTS`, but §75's gate states omit it. | One state set: PASS, NOT_APPLICABLE, PASS_WITH_REVIEW, INCOMPLETE_FACTS, UNKNOWN, EXPIRED, CONFLICT, BLOCKED (`decision.py`). | FIXED |
| C-03 | §95 shows GREEN as "**COMPLIANT** / VERIFIED". §12 and §121 forbid claiming compliance. | GREEN now means "controls passed". The word *compliant* never appears in output. | FIXED |
| C-04 | §11 `status` / `proposal_or_final` and §93's lifecycle conflate **what the law is doing** with **how far BAU has implemented it**. The FTC click-to-cancel rule shows why: it was final, then **vacated** (8th Cir., 2025-07-08), then re-proposed (ANPRM 2026-03-11). | Two fields: `legal_status` (proposed / enacted / effective / enjoined / vacated / superseded / repealed / industry_requirement / standard / guidance) and `bau_status` (PROPOSED to ACTIVE). | FIXED |
| C-05 | §20 says deletion must reach logs. §35 says never delete evidence. §97 makes the audit log immutable. With personal data in the audit log, all three cannot hold. | The audit chain **refuses** personal fields; it stores pseudonymous `ref:` hashes only. Deletion can be honoured without breaking the chain. | FIXED (`audit.py::_check_pii`) |
| C-06 | §49 (six-level permission scale) and §73 (five-level financial scale) are separate ladders. | Financial levels are mapped onto the general ladder (`permissions.py::FINANCIAL`). | FIXED |
| C-07 | §5 wipe gate requires "OS LICENSE VERIFIED". §3.2 says the chosen OS (aiOS) is **noncommercial**. As written, the commercial build can never pass the gate. | Debian is the base OS: free licence, commercial use allowed. aiOS stays an optional future foundation behind its licence gate (`wipe_gate.FOUNDATIONS`). §3's own rule ("replace the OS without rebuilding BAU") makes this legitimate. | FIXED |
| C-08 | §90 says "no uncontrolled auto-update of critical components". Unpatched security holes are themselves a §107 critical failure. | Debian **security** archive updates are automatic. Everything else goes TEST, then CANARY, then PROMOTE. | FIXED (unattended-upgrades restricted to `-security`) |
| C-09 | §22 cites the FTC **negative-option rule** as the basis for cancellation requirements. That rule's 2024 amendments were **vacated** before taking effect. | Registry cites ROSCA plus FTC Act s.5 (the Shutterstock basis) and California's ARL (AB 2863). The vacated rule is recorded as `vacated` so nobody cites it again. Controls are unchanged; only their legal basis is corrected. | FIXED |
| C-10 | §13 states EU AI Act Art. 50 timing without the **Digital Omnibus** (Reg. (EU) 2026/1744, in force 2026-07-27). | Art. 50 applies from 2026-08-02. Art. 50(2) marking for systems already on the market applies from 2026-12-02. High-risk duties moved to 2027-12-02 / 2028-08-02. | FIXED (registry) |
| C-11 | §32 says ADMT requirements begin "2027". The CCPA package actually staggers several dates: risk assessments from 2026-01-01 (attestations 2028-04-01); ADMT 2027-01-01; cybersecurity audits 2028-2030 by revenue tier. | Recorded with a verification note (secondary sources disagree on one tier). | FIXED |
| C-12 | §42 MAYA memory uses a SHA-256 chain and §97 uses an audit chain, but neither is **signed or anchored**. Anyone who can write the file can rebuild a consistent chain. | Records are HMAC-signed with a machine key. `bau audit anchor` exports the head hash for off-machine storage. | FIXED (anchoring is an operator step) |
| C-13 | §8 (pipeline), §7 (Jarvis steps) and §125 (loop) put **disclosure** in different places. §125 places it after execution. | Disclosure is a **pre-publication gate** (`publish` domain), checked before anything is published or sent. §125's "DISCLOSE / RECORD" stays as the recording step. | AMENDED (D-2) |
| C-14 | §28 targets WCAG 2.2 AA, but §29 demands GUI + CLI + palette + shortcut for every operation. No GUI exists yet. | The CLI is the accessible baseline today (keyboard-only, screen-reader friendly text/JSON). GNOME + Orca are installed. GUI acceptance remains OPEN. | OPEN |

## Part C: Loose ends (implementation would stall here)

| # | Loose end | Resolution |
|---|-----------|------------|
| L-01 | "Unknown jurisdiction" handling is not defined. | Unknown location gets the **strictest union** of every rule set BAU has. A jurisdiction with no rule set is UNKNOWN (escalate). One that is only partly covered needs human review. **FIXED** |
| L-02 | Policies could reference regulations that do not exist. | The policy compiler **refuses to load** on any dangling reference. **FIXED** |
| L-03 | §92 Regulation Watcher has no mechanism. | `bau reg watch` (daily systemd timer) hashes each official source page and flags changes as *discovered* (never auto-applied). Review dates turn RED when missed. **FIXED** (discovery). Semantic diffing of legal text: OPEN. |
| L-04 | Where does the §4 audit run if the laptop still runs Windows? | `hw-audit-windows.ps1` documents the Windows state. The wipe gate needs a Linux disk baseline from a Debian live session (`INSTALL.md`). **FIXED** |
| L-05 | §5 has no binding between "human confirmed" and the actual installer. | The wipe gate needs a typed disk serial and writes a short-lived record. `install.sh` imports it into the new audit chain, or marks the install **UNGATED**. The Debian partitioner also asks independently (nothing is preseeded). **FIXED** |
| L-06 | §105 "backup testing": the spec says test, but not how. | `bau backup verify` re-reads every file from the backup medium and hash-checks it. It refuses VERIFIED if secret-bearing files are present and encryption is unconfirmed. **FIXED** |
| L-07 | §79 cancellation regression test: nothing records when it last ran. | `cancellation_test_passed_at` older than 30 days **blocks** the offer. **FIXED** |
| L-08 | §25 claims registry exists but nothing reads it. | Email preflight scans copy. Any risky claim without an unexpired registry entry blocks. **FIXED** |
| L-09 | §82 data-use rights (view/store/train/...) are listed but not enforced. | OPEN: needs the data-object registry (§17) wired into the model router. |
| L-10 | §83 provider boundary: the router could send sensitive data to a cloud provider. | Provider registry records `training_on_customer_data`, retention and jurisdiction. Router enforcement is OPEN (router not built). |
| L-11 | EU member-state variations of ePrivacy (e.g. B2B email rules) are not modelled. | Member states are covered by the EU record. National deltas are OPEN; the registry note says so. |
| L-12 | US state privacy laws (~20) are collapsed into one placeholder record. | OPEN: one record per state before marketing to residents at scale. |
| L-13 | Tax thresholds: the spec rightly says "never hard-code" but ships none. | `tax/nexus_rules.yaml` format plus engine. An unverified rule always returns UNKNOWN. **CPA must fill the rules** (OPEN). |
| L-14 | MCP / agent / model registries are specified but have no validation. | `bau registry` enforces the required fields. It also refuses root for agents, routing to abliterated/unknown models, and "local" models without a benchmark. **FIXED** |
| L-15 | Media pipelines re-encode files and silently **strip C2PA / watermarks**. That breaks EU Art. 50(2) and California's AI Transparency Act for licensees. | `pub.provenance_preserved` blocks publication when the input carried a marking and the output does not. **FIXED** |
| L-16 | §88 "REVALIDATE AUTH" after reboot is undefined. | `bau recover` checks that key files exist and verifies the audit chain and registries before resuming jobs. **FIXED** (OAuth token revalidation per connector: OPEN). |

## Part D: Normative amendments (Spec v1.1)

These amend the master spec. Where they conflict with v1.0, v1.1 governs.

- **D-1 Base OS.** The base OS is Debian stable (13+), installed with LUKS full-disk encryption. aiOS is an optional foundation, enabled only once a commercial licence is held (§3.2 gate). BAU must remain installable on either.
- **D-2 Order of operations for anything that leaves the machine** (publish, send, sell, bill). The gates run in this order:
  1. Classify.
  2. Jurisdiction.
  3. Consent / rights.
  4. Suppression / opt-outs.
  5. Identity and authentication.
  6. Content truthfulness and claims.
  7. AI / synthetic disclosure.
  8. Required notices (address, terms, pricing).
  9. Opt-out / cancellation mechanism.
  10. Reputation and limits.
  11. Approval.
  12. Execute.
  13. Evidence.

  Disclosure is a pre-condition, never a post-step.
- **D-3 Outbound communications** are a first-class compliance domain (G-01). Every commercial email and marketing text passes `bau email preflight` / `bau sms preflight`. Opt-outs are global across channels and brands. BAU honours them immediately; the strictest external clock is 2 days (mailbox providers).
- **D-4 Gate states** are the eight in `decision.py`. Only PASS proceeds alone. PASS_WITH_REVIEW proceeds with a signed human approval. Everything else stops.
- **D-5 Asymmetry rule.** An unverified regulation may restrict, never permit. A pass against a rule not yet ACTIVE is PASS_WITH_REVIEW.
- **D-6 Strictest-union rule** for unknown locations (L-01).
- **D-7 Approvals** are signed by an individual human's own SSH key and verified against a root-owned allowed-signers list. Agents run as `bau`, which can verify approvals but never create one.
- **D-8 No personal data in the audit chain**; pseudonymous references only.
- **D-9 Payments:** BAU never receives, stores or logs card data. Use a PCI-validated processor's hosted checkout, complete the SAQ annually, and monitor payment-page scripts.
- **D-10 Incidents** carry a notification clock per affected jurisdiction from the registry. Evidence is preserved, never deleted.
- **D-11 Sanctions:** payees and customers above a configured value are screened before money moves.
- **D-12 Business prerequisites** (not software, but blocking for §23 "first revenue mission"):
  - entity formed;
  - EIN;
  - business bank account;
  - sales-tax permits where nexus is CONFIRMED;
  - physical postal address or registered PO box/CMRA for email footers;
  - business insurance (E&O / cyber) considered;
  - counsel identified for the §120 legal review queue;
  - CPA identified for §68-72.
- **D-13 Dashboard vocabulary:** GREEN = controls passed. The words "compliant", "legally protected" and "guaranteed" never appear in system output (§121, §24).

## Part E: What remains before "production-ready" (spec §106-107)

`bau status` shows this live from `reports/build_state.yaml`. As of this commit, these §107 critical conditions are still open, and on purpose the system reports itself **not production-ready**:

1. Counsel has not signed off any regulation (all are `IMPLEMENTED`, none `ACTIVE`).
2. No sending domain has verified SPF/DKIM/DMARC. The FCC wireless list is not loaded.
3. The recovery image has not been restore-tested on the actual laptop.
4. Tax nexus rules are not filled in by a CPA.
5. The sandbox runner profiles for untrusted code are not written (Podman is installed).
6. The real storefront's cancellation path does not exist yet, so it cannot be regression-tested.

All spec layers now have tested code: Jarvis, agents, model router, MCP router, MAYA memory, Project Genesis, media/music/spatial, factories, Opportunity Miner, economics, accounting, sanctions, incidents, legal pages, platforms, sandbox, accessibility, golden baseline and Mission Control. Third-party projects named in the spec (aiOS, open-context, Open-Generative-AI, God's Eye UI, Heretic, MAYA repos) connect through adapters only after Sentinel review.
