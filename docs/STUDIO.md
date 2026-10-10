# Studio: AI video clips you pay for per clip

The studio makes short AI video clips with **Higgsfield** (Kling 3.0 models) for your
channels and music videos. You pay Higgsfield per clip from a balance you top up. BAU
keeps the spending inside a budget **you** set, shows the price of every clip before it
is made, and only makes a clip when you confirm it.

## Before you start: what Higgsfield's terms say

Checked 2026-10-10 in Higgsfield's help centre and API docs:

- **You own the clips** you make, and you may use them commercially (ads, client work,
  YouTube).
- **Higgsfield may use what you send and make to train its AI**, for as long as it is kept
  on Higgsfield. That stops when you delete the content or your account. So never put
  personal details or real people's names or faces in a prompt.
- **Failed clips and clips rejected by content moderation are not charged.**
- Finished clips stay on Higgsfield for **at least 7 days**. BAU downloads each one, so
  you keep it.
- Your Higgsfield account has a limit on how many clips can be in progress at once.

Full terms: https://higgsfield.ai/terms-of-use-agreement. Read them before step 3.

## Once: set it up (about 10 minutes)

1. **Get an API key.** Go to https://console.higgsfield.ai, sign in, add a balance, and
   create an API key. You get a **key ID** and a **key secret**.
2. **Give the key to BAU.**
   - **Codespace:** on github.com go to your profile picture > **Settings** >
     **Codespaces** > **New secret**. Add two secrets, both for the `linux-ai-biz`
     repository:
     - `HIGGSFIELD_API_KEY_ID` with the key ID;
     - `HIGGSFIELD_API_KEY_SECRET` with the secret.

     Then stop and restart the codespace.
   - **Laptop:** add the same two lines to `/etc/bau/models.env`.

   Never paste the key into a chat or a file in the repository.
3. **Approve Higgsfield.** This is your decision, made after reading its terms:
   ```bash
   bau set-status provider higgsfield APPROVED
   ```
4. **Set your budget.** Choose your own numbers. This example allows $40 a month and at
   most $3 for any one clip:
   ```bash
   bau video budget --monthly 40 --per-clip 3
   ```
   Until you do this, the studio spends nothing.

## Make a clip

**On the Jarvis screen:**
1. Click **Studio**.
2. Write what the clip should show, then pick the model, length (3-15 s), shape (16:9,
   9:16 for Shorts and TikTok, or 1:1) and sound.
3. Press **Price it**. A box shows the exact price and what is left this month.
4. Press **Confirm** to make it, or **Not now**.

The Studio dot spins while the clip is being made. **Check clips** brings it in when it is
ready, and **Play** shows it.

**In the terminal:**
```bash
bau video quote "A paper boat on a pond at dawn, gentle camera push-in" --model kling-3-std
bau video make  "A paper boat on a pond at dawn, gentle camera push-in" --model kling-3-std --aspect 9:16
bau video clips --wait 600
```
`make` shows the price and asks `Make it? [y/N]`. Saved clips are in `studio/clips/`
inside your BAU folder, each with a `.provenance.json` record saying it is AI-generated.

**Asking Jarvis:** say something like "make a 5-second clip of a paper boat at dawn". Jarvis
puts the priced clip on your screen. Only your Confirm makes it.

## The models

| Model | When to use it |
|---|---|
| `kling-3-turbo` | Fast drafts and ideas |
| `kling-3-std` | Everyday clips |
| `kling-3-pro` | Final, best-looking shots |

Prices change, so BAU always asks Higgsfield for the price of the exact clip first.

## What protects your money

- **No budget, no spending.** You set the budget yourself, and nothing changes it but you.
- **Priced before it starts.** A clip that costs more than your per-clip limit, or more
  than what is left this month, is refused before anything is sent.
- **Only you start a clip.** Jarvis can suggest one. Your **Confirm** (or `y` in the
  terminal) starts it.
- **HOLD stops it.** When BAU is on HOLD, no new clips start.
- **Spending is recorded.** Every finished clip's cost goes into BAU's ledger, so the
  Watchdog's daily spending limit counts it, and into the tamper-evident record.
  Clips that fail or are rejected are not recorded as spending, because Higgsfield
  doesn't charge for them.
- **AI clips are labelled.** Each saved clip is marked AI-generated. When you post one,
  YouTube and TikTok's AI labels are set as usual.
