# BAU/BSA: Compliance-First AI Business Computer

The foundation of the BAU/BSA autonomous business platform:
- a **USB installer** that turns a laptop into an encrypted, hardened Debian machine;
- the **BAU control plane**, where compliance is part of the machine rather than a document beside it.

Before BAU sends an email, texts someone, publishes generated media, sells a subscription, monetizes an asset or moves money, it:
1. determines which rules apply on that date, in that jurisdiction;
2. decides PASS / REVIEW / BLOCK;
3. records the evidence in a tamper-evident audit chain.

> BAU never claims to be "compliant" or "legally protected" (spec §121). It reports which requirements it identified, which controls ran, what evidence exists, and what is unresolved. Every regulation ships **awaiting counsel sign-off**, so nothing gets a clean PASS until a qualified human reviews it.

## Quick start

```bash
python3 -m pip install -e '.[dev]'
bau init                                   # BAU_HOME (default ~/.bau, or /var/lib/bau when installed)
bau reg validate                           # 46 regulations, 59 policies, all cross-references resolve
bau status --brief                         # honest production-readiness dashboard
bau email preflight --message m.json --recipients r.json --sender s.json --evidence
python3 -m pytest -q                       # full test suite
```

## Install on the laptop (two USB sticks)

```bash
installer/make-payload.sh --to /media/$USER/USB2         # USB #2: BAU payload + pre-wipe tools
installer/build-usb-image.sh                             # USB #1: verified Debian + BAU preseed
sudo installer/write-usb.sh dist/bau-debian-*.iso /dev/sdX
```

Then follow **[docs/INSTALL.md](docs/INSTALL.md)** in order: audit, backup and verify, wipe gate, install the OS, install BAU.

## Documents

| Document | What it is |
|---|---|
| [docs/SPEC_GAP_ANALYSIS.md](docs/SPEC_GAP_ANALYSIS.md) | Loose ends, contradictions and missing laws found in the master spec, and how each was resolved (spec v1.1 amendments) |
| [docs/EMAIL_AND_MESSAGING_COMPLIANCE.md](docs/EMAIL_AND_MESSAGING_COMPLIANCE.md) | The exact order every commercial email and marketing text goes through, and what you must set up |
| [docs/REGULATORY_STATUS.md](docs/REGULATORY_STATUS.md) | What changed in the law through 2026-10-04, with sources |
| [docs/INSTALL.md](docs/INSTALL.md) | Phase-by-phase install runbook |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the spec maps onto the code; decision model; identities |
| [docs/spec/BAU_MASTER_SPEC.md](docs/spec/BAU_MASTER_SPEC.md) | The master specification (v1.0) |

## Layout

```
src/bau/
  decision.py  policy.py  regulations.py  jurisdiction.py   # compliance engine
  audit.py  evidence.py  status.py  jobs.py  registry.py    # trust plane, recovery, dashboard
  comms/        email, SMS, consent ledger, suppression, DNS auth
  commerce/     subscriptions + cancellation, IP + royalties, tax nexus
  privacy/      data-subject rights with deletion propagation
  security/     permissions + approvals, secret scanner, Sentinel repo intake
  disclosure.py claims.py hardware.py backup.py wipe_gate.py cli.py
  data/regulations/*.yaml  data/policies/*.yaml  data/build_state.yaml
installer/      build-usb-image.sh  write-usb.sh  make-payload.sh  hw-audit*.{sh,ps1}
                preseed/  firstboot/  payload/{install.sh, systemd/, hardening/}
tests/          engine, email/SMS, commerce/disclosure, trust plane, CLI
```

## Status

Foundation complete and tested.

Not yet built:
- Jarvis orchestration, the model router and Project Genesis;
- MAYA memory;
- the media and spatial adapters, and the business factories.

Each depends on third-party repositories that must pass Sentinel first. `bau status` tracks the full acceptance suite (spec §106).
