# Regulatory Status Snapshot: 2026-10-04

This is the human-readable companion to the machine-readable registry in `src/bau/data/regulations/`. Run `bau reg list` for the live view. Each record keeps its own `source_url`, `last_verified`, `next_review` and, where the official text was not yet read, a `verification_note`.

**How this was verified:** web research on 2026-10-04 against official pages where reachable, plus law-firm and trade analyses where official text was not checked. Records whose facts came only from secondary sources say so. All records ship with `bau_status` below ACTIVE, so the system asks for human review until counsel signs off.

## Changes since the spec was written

| Topic | Status | Effect on BAU |
|---|---|---|
| FTC click-to-cancel (2024 Negative Option amendments) | **Vacated**, 8th Cir., 2025-07-08. **ANPRM** issued 2026-03-11 (not law). | Cancellation controls are unchanged; their legal basis is ROSCA, FTC Act s.5 and state ARLs. |
| FTC v. Shutterstock | Settled 2026-05-13, **$35M** | Disclosure of "annual, paid monthly" commitments and cancellation fees is enforced (`sub.disclosure`). |
| EU AI Act Art. 50 | Applies **2026-08-02**. Art. 50(2) marking for existing systems by **2026-12-02** (Digital Omnibus, Reg. (EU) 2026/1744, in force 2026-07-27). | `pub.eu.*` policies |
| EU AI Act high-risk | Moved to **2027-12-02** (Annex III) and **2028-08-02** (Annex I) | Recorded as `enacted`, future-dated |
| California AI Transparency Act (SB 942 + AB 853) | Operative **2026-08-02** for large GenAI providers; hosting platforms 2027-01-01 | BAU must **not strip** provider provenance markings |
| New York synthetic performer ad disclosure | Effective **2026-06-09** | `pub.ny.synthetic_performer`, `email.synthetic_performer` |
| California SB 1050 (synthetic performers in video/audio ads) | **Signed 2026-09-16**; operative date unconfirmed | Enforced now as a precaution |
| California AB 1609 (customer-service chatbots, $500M+ revenue businesses) | **Signed 2026-09-28** | BAU discloses bots everywhere regardless |
| California SB 923 (CCPA deletion covers all PI) / AB 883 (data broker 30-day DSR) | Signed 2026-09-27 | Deletion propagation covers every store |
| California minors (AB 1709, AB 2246, AB 1856) | Signed 2026-09-10 | BAU does not market to minors |
| CCPA ADMT / risk assessment / cybersecurity audit regs | Effective 2026-01-01; ADMT 2027-01-01; audits 2028-2030 by tier | Recorded |
| UK Data (Use and Access) Act: PECR | In force **2026-02-05**; fines up to GBP 17.5M / 4% | `uk-pecr-duaa` |
| TCPA revocation rule | In force 2025-04-11; cross-purpose waiver expired 2026-04-11 | Revocation is global |
| Texas SB 140 | Effective 2025-09-01; consent-based texts exempt from registration (Nov 2025 settlement) | Keep consent evidence |
| Gmail / Yahoo / Microsoft bulk-sender rules | Rejection enforcement since Nov 2025 | `email.auth.*`, `email.unsubscribe.one_click`, `email.reputation.*` |
| COPPA 2025 amendments | Compliance date 2026-04-22 | Recorded |
| FTC civil penalty maximum | $53,088 (2025 level, unchanged in 2026) | Recorded on each FTC rule |
| 1099-NEC / 1099-MISC threshold | $600 -> **$2,000** for payments from 2026 (One Big Beautiful Bill Act) | `accounting.THRESHOLDS`; royalties keep the $10 line (confirm with CPA) |
| OFAC Syria program | Comprehensive sanctions ended 2025-07-01; regulations removed 2025-08-26 | Embargo list: Cuba, Iran, North Korea, Crimea, so-called DNR/LNR; SDN screening still applies |

## Sources consulted (2026-10-04)

- FTC CAN-SPAM guide: https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business
- Click-to-cancel status: Sidley (Feb 2026), Jones Day (May 2026), Crowell, Goodwin, Davis+Gilbert analyses of the 2026 ANPRM
- Shutterstock settlement: Proskauer (2026-07-24), Inside Privacy / Covington, Regulatory Oversight (May 2026)
- Mailbox sender rules: Google https://support.google.com/a/answer/81126, Yahoo https://senders.yahooinc.com/best-practices/
- EU AI Act / Digital Omnibus: Jones Walker, Cloud Security Alliance research note (2026-07-29), Plesner, Usercentrics
- California AI Transparency Act: National Law Review, CASRAI
- New York synthetic performer law: Hunton (S.8420-A signed 2025-12-11), News12 (2026-06-10)
- California 2026 session: Office of the Governor (2026-09-16, 2026-09-28); Kelley Drye session wrap-up
- CCPA regulations: CPPA https://cppa.ca.gov/regulations/ ; Hunton, Thompson Coburn, DLA Piper
- UK DUAA / PECR: Weightmans, Hill Dickinson, Freeths
- TCPA / Texas SB 140: Kelley Drye, Thompson Hine, Commlaw Group
- FTC penalty adjustment: FTC Rule 1.98 reporting (2025 adjustment; 2026 unchanged)
- 1099 threshold: Beancount OBBBA guides (2026); OFAC Syria: Hunton, OFAC FAQs (2025-06-30), Simpson Thacher

## Re-verification schedule

Every record carries `next_review` (mostly 2027-01-04; fast-moving items 2026-11 / 2026-12). On that date the record turns **EXPIRED**: decisions relying on it stop until someone re-verifies it. The daily `bau-regwatch` timer also hashes each official source page and flags changes.
