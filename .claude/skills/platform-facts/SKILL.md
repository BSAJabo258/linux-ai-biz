---
name: platform-facts
description: Check and record platform and law facts for the adult virtual creator (Fanvue, Instagram, TikTok; Michigan, US) from official pages with the date, before any code depends on them. Use when adding or changing a platform, posting API, AI-label rule, payout or tax rule, or regulation record, and for "what are Fanvue's rules", "is this allowed on Instagram", "Michigan rules".
---

# Platform facts

The owner's rule (CLAUDE.md): platform facts are verified, never written from memory. A
wrong fact here means a blocked account, a removed post or a legal problem. Never write
"compliant", "guaranteed" or "risk-free": BAU reports requirements and evidence, and every
regulation record waits for counsel review.

## 1. Find the official source

- Platforms: the platform's own developer docs, terms and community rules (for example
  developers.tiktok.com, developers.facebook.com for Instagram, Fanvue's own help and terms
  pages). A blog or forum is a lead to the official page, never the source itself.
- Laws: the statute or the regulator's page (legislature.mi.gov for Michigan, the FTC, the
  US Code). Note the bill or section number.
- Read the page itself. If it cannot be fetched, say so: do not fill the gap from memory.

## 2. Write down what it says, with the date

- In the module that uses it: a docstring block "API facts verified YYYY-MM-DD against
  <site>" listing endpoints, scopes, limits and labels (see `src/bau/tiktok.py`).
- A platform policy record: `examples/platform-<name>.yaml` with `last_verified`, the AI
  label rule, automation rule, limits and appeal process (see
  `examples/platform-tiktok.yaml`). Load it with `bau platform add FILE`.
- Laws: a record in `src/bau/data/regulations/*.yaml` (reg_id, law, status, obligations,
  source link and date). Policies in `src/bau/data/policies/*.yaml` cite it by `reg_id`;
  the loader refuses a reference to a reg_id that does not exist.

## 3. Keep claims apart from facts

For each fact write which kind it is: **read on the official page (date, link)**, **only
claimed** (a third party says so) or **unknown**. An unknown stays unknown. The owner
decides what to do about it.

## 4. Check

```bash
bau reg validate                 # regulations and policies agree
bash scripts/check.sh            # must say ALL PASS
```

Platform rules for this business, from CLAUDE.md:

- adults only, 21+, fictional;
- no real person's likeness;
- an AI label on every post;
- explicit content only to Fanvue;
- Instagram and TikTok get sfw posts only.

A platform rule found that is stricter than BAU's goes into the policy record and, where
code posts, into a test that plants the bad case and sees it refused.
