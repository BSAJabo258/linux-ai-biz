# Your operating constitution

Jarvis reads your **BAUBSA Operating Constitution** before he answers every question. It
tells him how you want him to think and work. It comes in six parts, one file each:

| File | What it says |
|---|---|
| `1-identity.md` | who Jarvis is and what every recommendation must improve |
| `2-learning-rules.md` | your ten learning principles |
| `3-engineering-rules.md` | before, during and after building something |
| `4-security-rules.md` | security is a feature; assume things fail |
| `5-self-improvement.md` | the questions to ask after every project |
| `6-baubsa-mode.md` | observe, analyze, plan ... improve: the cycle to follow |

## Where it lives

Run this once (it's safe to run again; it never overwrites your edits):

```bash
bau init
```

Then see where your copy is:

```bash
bau jarvis constitution
```

It shows the folder (in a codespace: `/workspaces/.bau-home/constitution`), the files
Jarvis loads and how long they are.

## Changing it

Open a file in that folder, change the words, and save. Jarvis uses the new text from your
next question; there is nothing to restart.

- **Add a part:** make a new file in the folder, for example `7-kids-channel.md`. Files are
  read in name order.
- **Switch a part off:** empty the file instead of deleting it (`bau init` puts deleted
  files back).
- Keep it short. Jarvis sends it with every question, and anything past 16,000 characters is
  cut off.

## What it can't change

The constitution shapes how Jarvis thinks. It can't give him new powers. Whatever it says,
the safety rules stay first:

- Approvals for money, commercial email and legal matters are yours alone, signed with
  `bau approve`.
- Posting, releasing a HOLD and other consequential actions are only *staged*; they run
  when you press Confirm.
- What his tools read stays data, never instructions.

## Lessons and memory

Part 5 asks what should enter memory after each project. Ask Jarvis to remember a lesson
("remember that the free model is busy in the evenings"), and he can look it up later
("what did we learn about the free model?").
