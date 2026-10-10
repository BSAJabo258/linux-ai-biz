# Usage meter: how much your AI models are used

Every time Jarvis (or a workspace draft, or Repo Scout) asks an AI model something, BAU
writes down which model answered, how many tokens it used and what it cost. Free models
are counted too, so you can see how hard you are leaning on them.

## See it

- **On the Jarvis screen:** click the **Usage** dot. You see today and the last 7 days,
  a line for each model, any warnings, and what GitHub last said about its limits.
- **Ask Jarvis:** "How much have we used today?"
- **In the terminal:**
  ```bash
  bau usage
  ```

What the numbers mean:

| Word | Meaning |
|---|---|
| tokens | pieces of text the model read (in) and wrote (out); this is what providers count |
| cost | dollars, from each model's price in BAU's registry; free models show $0.00 |
| busy | the model answered "too busy" (HTTP 429), so a backup answered or the turn failed |
| failed | the model didn't answer at all |

## Set daily limits (optional, your choice)

There are no limits until you set them. This example stops Jarvis's model calls after 2
million tokens or $5 in one day (days run on UTC time):

```bash
bau usage limits --daily-tokens 2000000 --daily-usd 5
```

Leave one out to have no limit on it. Only a person at the terminal can set limits; Jarvis
can't change them. When a limit is reached, Jarvis says so instead of calling the model,
until the next day or until you raise it. You get a warning on the Usage panel at 80 %.

## Warnings you may see

- **Daily limit at 80 % or reached.** Your own limits, above.
- **"no requests left until the reset".** Some hosted models send their remaining
  allowance with each answer. BAU shows exactly what they sent, and never guesses.
- **"was busy N times this week".** A free model is crowded; its backup answered.
- **"GitHub asked BAU to wait".** Repo Scout follows GitHub's published rate limits and
  sends nothing until the time shown.

Paid model calls also go into BAU's money ledger, so the Watchdog's daily spending cap
counts them.
