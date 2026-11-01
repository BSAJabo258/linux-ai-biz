# Virtual creator channel

BAU can draft repeatable social content for a fictional adult virtual creator. A profile
stores the creator's stable visual traits, voice, niche, disclosure setting, boundaries, and
owner-reviewed platform rules. Each batch carries the same identity lock into every image
or video prompt, while varying the shot and creative angle.

## Create a profile

```bash
bau creator init
```

This puts the starter profile (Aria) where Jarvis looks, `BAU_HOME/creators/aria.yaml`
(`/var/lib/bau/creators/aria.yaml` on the installed laptop). Jarvis can plan her posts right
away: say "Plan seven Instagram posts about a cozy autumn week." With only one profile he uses
it without being told her name. `--out PATH` puts it somewhere else.

Edit the copied YAML before use. The profile must describe a fictional person aged 21 or
older, enable AI disclosure, list at least four stable appearance traits, and define content
and likeness boundaries. `platform_rules` is a per-platform map maintained by the owner;
BAU does not claim it is a complete or current legal/policy checklist.

```yaml
platform_rules:
  instagram:
    - Use the platform's current AI-content disclosure controls.
    - Keep the asset within the account's current content rules.
  fanvue:
    - Follow the platform's current AI persona and adult-content requirements.
```

Run `bau creator check "$BAU_HOME/creators/aria.yaml"` to validate the profile. Then draft a
week of post prompts:

```bash
bau creator batch "$BAU_HOME/creators/aria.yaml" "autumn city fashion" \
  --platform instagram --count 7 --out "$BAU_HOME/creators/aria-week-01.md"
```

## Two tiers: sfw and explicit

Every batch has a tier. `sfw` (the default) is for mainstream platforms: Instagram, TikTok,
YouTube, X and Patreon only ever get `sfw`. `explicit` is for adult platforms with
age-verified audiences; today that is `fanvue`. BAU refuses an explicit batch until you write
your own limits in the profile:

```yaml
explicit_boundaries:
  - adults only, consenting, fictional persona
  - no real-person likeness, no non-consent, no violence
```

Then:

```bash
bau creator batch "$BAU_HOME/creators/aria.yaml" "evening in" \
  --platform fanvue --tier explicit --count 5 --out "$BAU_HOME/creators/aria-fv-01.md"
```

Explicit prompts are marked for the local content lane model (local only, no tools, never
minors). Jarvis only drafts `sfw` batches; explicit ones are always your own command. In
every tier, youth-coded words ("barely legal", "schoolgirl", any age under 18, and others)
are refused.

The batch includes an identity lock, distinct visual prompts, caption briefs that disclose
the AI persona, and a review checklist for every post. It does not call an image/video
provider or publish anything. Review the provider's terms and the platform's current rules
before generating or posting; a profile's platform rules are owner-maintained reminders,
not a legal determination. Paid media generation and publication remain under the existing
human confirmation controls.

Jarvis can also return a batch in conversation when the profile is saved as
`$BAU_HOME/creators/<id>.yaml`, for example: “Draft seven Instagram posts for Aria about
autumn city fashion.” The starter profile id is `aria`.

To plan a whole week stage by stage, with your check on each stage, use the
`creator-week` workspace: `bau ws create creator-week`, then `bau ws episode creator-week
"this week's theme"` (docs/WORKSPACES.md). Its `no_minors` check runs on every drafted stage.
