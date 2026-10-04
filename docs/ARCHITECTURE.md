# Architecture: How the Spec Maps to This Code

## Principle

BAU owns the control plane; everything else is a replaceable capability (spec §0, §111-112). This repository is the **trust plane + compliance control plane + installer**: the part everything else must pass through. Models, agents, media engines and factories plug in later as adapters behind it.

```
           objective / job
                 |
      +----------v-----------+      facts      +------------------+
      | domain fact extractor | --------------> |  policy compiler |  <- policies/*.yaml
      | email sms subscription|                 |  (one decision   |  <- regulations/*.yaml
      | publish chatbot ip    |                 |   path)          |     (legal_status x bau_status,
      +-----------------------+                 +--------+---------+      dates, sources)
                                                         | Decision (8 states)
                        +--------------------------------+-------------------+
                        |                                |                   |
                 PASS -> proceed       PASS_WITH_REVIEW -> signed human approval    else -> stop
                        |                                |
                        +----------> evidence package + hash-chained, HMAC-signed audit log
```

## The decision model (`decision.py`, `policy.py`)

**States:**
- PASS
- NOT_APPLICABLE
- PASS_WITH_REVIEW
- INCOMPLETE_FACTS
- UNKNOWN
- EXPIRED
- CONFLICT
- BLOCKED

When findings are combined, the worst state wins. An empty evaluation is UNKNOWN, never PASS.

**Three-valued logic:** a missing fact is `None`, which can only produce INCOMPLETE_FACTS, never a pass.

**Date-awareness:** each regulation computes `in_force | future | unknown_date | not_law | dead` for the decision date:
- vacated/repealed rules are not enforced;
- proposed rules are not law;
- enacted rules with an unknown operative date are enforced as a precaution.

**Asymmetry:**
- a failing requirement blocks whatever the review status of its regulation;
- a passing one gives a clean PASS only when every cited regulation is ACTIVE (human-signed);
- a regulation past `next_review` turns a pass into EXPIRED.

**Jurisdiction:**
- ISO 3166 codes (`CA` = Canada, `US-CA` = California).
- An unknown location expands to the strictest union of every rule set.
- Each domain declares its `coverage`. A jurisdiction outside it is UNKNOWN, or PASS_WITH_REVIEW if only partly covered.

**Conflict:** policies may `set` a value (e.g. `consent_model`). Differing values resolve to the strictest when an ordering is declared; otherwise the result is CONFLICT (spec §117).

**Compile-time safety:** an unknown operator, unknown on_fail state, duplicate ID or **reference to a nonexistent regulation** refuses to load.

## Spec section → implementation

| Spec | Implementation |
|---|---|
| §1.4 secrets | `security/secrets_scan.py`, CI secret scan, keys generated on-machine in `/etc/bau` |
| §1.5, §96-97 evidence + audit | `audit.py` (hash chain, HMAC, PII refusal, anchor), `evidence.py` |
| §4 hardware gate | `hardware.py`, `installer/hw-audit.sh`, `hw-audit-windows.ps1` |
| §4.1, §104-105 backup | `backup.py` (manifest + read-back verify) |
| §5 wipe gate | `wipe_gate.py`, `bau wipe-gate`, `write-usb.sh` record, `install.sh` import |
| §3, §90 OS + golden baseline | `installer/` (Debian, LUKS, preseed, hardening); golden image = OPEN |
| §9-12, §74-75, §113-118 compliance engine | `regulations.py`, `policy.py`, `decision.py`, `jurisdiction.py` |
| §13-16, §77, §80-81 AI disclosure + likeness | `disclosure.py`, `policies/ai_disclosure.yaml` |
| §17-20 data governance + rights | `privacy/dsr.py` (deadlines, per-store deletion outcomes) |
| §21 consent | `comms/consent.py` (ledger with evidence, CASL expiry, global withdrawal) |
| §22-23, §79 subscriptions + cancellation | `commerce/subscriptions.py`, `policies/commerce.yaml` |
| §24-25 claims | `claims.py` |
| §36-37, §111 Sentinel | `security/sentinel.py` (static only, canonical state machine) |
| §43-51 registries | `registry.py` |
| §49, §55, §73 permissions / revocation / money | `security/permissions.py` (SSH-signed human approvals, `bau approve`) |
| §66-67 IP + royalties | `commerce/ip.py` (exact decimal splits, refuses unresolved ownership) |
| §68-71 tax nexus | `commerce/tax.py` (rules as dated, verified data; unverified = UNKNOWN) |
| §86-89 jobs, checkpoints, recovery | `jobs.py`, `bau recover`, `bau-recover.service` |
| §92-93 regulation watcher | `regulations.watch`, `bau reg watch`, `bau-regwatch.timer`; lifecycle via `bau reg promote` |
| §95, §106-107 dashboard | `status.py`, `data/build_state.yaml` |
| Outbound comms (gap G-01) | `comms/email.py`, `comms/sms.py`, `comms/dns_auth.py` |

Not yet built (each enters through Sentinel first):
- Jarvis (§7)
- model router (§45)
- MCP router (§50-51 runtime)
- Project Genesis (§38-41)
- MAYA Memory Lane (§42)
- media/spatial adapters (§56-59)
- business factories (§60-65)
- the GUI (§28-30)

## Runtime layout

| Path | Owner / mode | Contents |
|---|---|---|
| `/opt/bau/venv` | root | the installed package |
| `/var/lib/bau` (`BAU_HOME`) | `bau:bau` 2770 | regulations, policies, audit, evidence, consent, suppression, dsr, jobs, reports... (spec §91 `.bau/` layout) |
| `/etc/bau/audit.key`, `unsubscribe.key` | `root:bau` 0640 | machine-generated |
| `/etc/bau/allowed_signers` | `root:bau` 0644 | public keys of the humans who may approve; only root can add one |
| `~bauadmin/.ssh/bau_approval_ed25519` | the admin, passphrase-protected | the admin's personal approval signing key |

## Identities

| Account | Can | Cannot |
|---|---|---|
| `bauadmin` (human, in `bau` + `bau-approvers`) | run everything; sign approvals with a personal key (`bau approve`); promote regulations (interactive TTY only) | approve a request it made itself |
| `bau` (service; agents run here) | read/write state, sign audit records, **verify** approvals | create an approval: it holds no signing key, and only root edits `allowed_signers` |
