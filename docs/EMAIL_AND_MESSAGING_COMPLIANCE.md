# Email and Text-Message Compliance: How BAU Sends, in Order

Status of the law as researched on **2026-10-04**. Sources are in `REGULATORY_STATUS.md`. Every rule below is a record in `src/bau/data/regulations/` and is enforced by `src/bau/data/policies/email.yaml` / `sms.yaml`. This is engineering, not legal advice. Have counsel review the records and promote them to ACTIVE (`bau reg promote`).

## What changed recently (and what did not)

- **No new federal email statute passed in 2026.** CAN-SPAM is still the US law. Its maximum penalty is **$53,088 per email** (2025 inflation adjustment; the FTC kept 2025 levels for 2026).
- **Mailbox providers now enforce.** Since November 2025, Gmail, Yahoo and Microsoft Outlook.com **reject** bulk mail that lacks:
  - SPF + DKIM + DMARC;
  - one-click unsubscribe;
  - a spam-complaint rate under 0.3%.

  This is the change that shuts businesses down fastest, because the mail simply stops arriving.
- **UK:** since **2026-02-05**, PECR fines for marketing email/SMS rose from GBP 500,000 to **GBP 17.5M or 4% of turnover**.
- **Texting (TCPA):**
  - Since 2025-04-11, people can revoke consent in **any reasonable way** ("stop", "leave me alone"), and you must honour it within 10 business days.
  - The FCC's temporary waiver on "revocation covers all message types" expired **2026-04-11**, so treat every STOP as STOP-everything.
  - Texas (SB 140, 2025-09-01) now treats marketing texts as telephone solicitation. Consent-based programs are exempt from registration.
- **AI in ads:**
  - New York requires conspicuous disclosure of AI-generated **synthetic performers** in ads (from **2026-06-09**; $1,000 / $5,000 per violation).
  - California signed **SB 1050** on **2026-09-16** (synthetic performers in video/audio ads); its operative date is not confirmed yet.
  - BAU enforces both now.
- **Subscriptions:**
  - The FTC "click-to-cancel" rule was **vacated** in 2025. The FTC restarted rulemaking (ANPRM, 2026-03-11).
  - Enforcement continues under ROSCA. **Shutterstock paid $35M** (May 2026) for hidden auto-renewal terms and hard cancellation.
  - California's ARL (AB 2863, 2025-07-01) already requires click-to-cancel.

## The order every commercial email goes through

`bau email preflight --message m.json --recipients r.json --sender s.json --evidence`

| Stage | Gate | Blocks when |
|---|---|---|
| 10 | **Classify** | Category not declared. Mixed messages with a commercial subject or opening count as commercial. |
| 20 | **List source** | Addresses were harvested, scraped, guessed, bought or rented. |
| 30 | **Jurisdiction** | Per recipient. **Unknown location = the strictest rules of every country BAU covers.** A country with no rule set is escalated. |
| 35 | **Minors** | The recipient is a known minor. |
| 40 | **Consent** | <ul><li>US: opt-in or an existing customer relationship. This is BAU policy; the law only requires opt-out.</li><li>Canada: CASL express consent, or implied consent (expires 2 years after a purchase, 6 months after an inquiry).</li><li>EU/UK: opt-in or soft opt-in.</li><li>Australia: express or inferred consent.</li></ul> |
| 50 | **Suppression** | The address opted out, complained, or was revoked on **any** channel. |
| 51-52 | **FCC wireless domains** | The FCC list is missing or over 30 days old, or the address is on a carrier domain without express authorization. |
| 60-62 | **Identity and authentication** | <ul><li>The From/Reply-To domain is not yours.</li><li>SPF, DKIM, DMARC (with `rua=` reporting) or TLS is missing.</li><li>The From domain is not aligned.</li></ul> |
| 70 | **Subject line** | Fake "RE:/FW:", fake account alarm, fake prize, fake "as we discussed" (sent to human review). |
| 80 | **Content** | <ul><li>A risky claim ("guaranteed", "risk-free", "100% accurate", earnings, "AI-powered") has no unexpired evidence in the claims registry.</li><li>A testimonial is unverified, or a material connection is undisclosed.</li><li>An AI synthetic performer is undisclosed (NY/CA).</li><li>The content is sexually explicit.</li><li>The message is not identified as an ad when the recipient never opted in (US).</li></ul> |
| 90 | **Postal address** | No valid physical postal address in the message (US, Canada). |
| 100-101 | **Unsubscribe** | <ul><li>There is no visible link.</li><li>Unsubscribing needs a login, costs a fee, or works for fewer than 30 days.</li><li>Opt-outs take more than 2 days to process.</li><li>The RFC 8058 `List-Unsubscribe` + `List-Unsubscribe-Post: List-Unsubscribe=One-Click` headers are missing.</li></ul> |
| 110-111 | **Reputation** | Spam-complaint rate is 0.3% or more (block); 0.1% or more needs review. |
| 120 | **Send + evidence** | Only recipients whose decision may proceed are returned as sendable. The evidence package and audit entry are written. |

Every stage must pass. A later stage never substitutes for an earlier one. A missing fact never counts as a pass: it is INCOMPLETE_FACTS and the send stops.

### What you must provide (one-time setup)

1. **A physical postal address** for the footer: a street address, or a registered PO box / commercial mail receiving agency.
2. **DNS on the sending domain:**
   - one SPF record (not `+all`);
   - DKIM via your email service provider;
   - DMARC starting at `p=none` with `rua=mailto:` reports, then tightened to `quarantine`.

   Check with `bau email check-dns yourdomain.com --selector <selector>`.
3. **The FCC wireless-domain list:** download it from the FCC, then run `bau email import-wireless-list FILE --fetched-at YYYY-MM-DD`. Refresh it monthly.
4. **A signup form that captures real consent:**
   - an unticked box;
   - the purpose stated;
   - double opt-in recommended.

   Record each signup with `bau consent ... --evidence-ref <hash of the form snapshot>`.
5. **An unsubscribe endpoint** that accepts the one-click POST with no login. Use `bau.comms.consent.UnsubscribeTokens`: the token holds only a salted hash, never the address, and cannot be forged. Generate headers with `bau email headers https://yourdomain/u/<token>`.

### After sending

- Unsubscribes, complaints (feedback loops) and hard bounces go straight to the global suppression list (`bau email suppress` / `bau email unsubscribe TOKEN`).
- Suppression stores only salted hashes. It survives a data-deletion request, which is the only way to keep honouring an opt-out for someone whose other data you deleted.

## Marketing text messages

`bau sms preflight --message m.json --recipient r.json`

1. Classify (marketing / informational / transactional).
2. Not revoked or suppressed on **any** channel.
3. **Prior express written consent** for marketing (TCPA, Florida FTSA, Texas SB 140).
4. National DNC and internal DNC scrub done.
5. **Quiet hours** in the recipient's local time: 8am-9pm federally, **8am-8pm in Florida**. An unknown timezone blocks the send.
6. Florida: at most 3 messages on one subject per 24 hours.
7. Brand named in the text, plus "Reply STOP to opt out".

Inbound replies go through `bau sms inbound`. "STOP", "quit", "please don't text me" and similar revoke consent everywhere, immediately.

Only US texting rules are modelled. A text to any other country returns UNKNOWN and cannot be sent until rules for that country are added.

## Penalty reference (for prioritising, not legal advice)

| Law | Exposure |
|---|---|
| CAN-SPAM | up to $53,088 per email |
| TCPA / Florida FTSA | $500-$1,500 per message, private lawsuits and class actions |
| CASL | up to CAD $10M per violation |
| GDPR / UK PECR | up to EUR 20M / GBP 17.5M or 4% of global turnover |
| NY synthetic performer | $1,000 first, $5,000 after |
| FTC ROSCA / s.5 | redress plus civil penalties (Shutterstock: $35M) |
| Mailbox providers | rejection: your email stops arriving |
