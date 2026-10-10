# Toolbox: tools other people already built

Most problems Jarvis meets have already been solved by someone: connecting a model to your
apps, stopping it making things up, giving it a memory, a voice, video editing, running a
free model on your own computer. The toolbox is BAU's list of the best-known open-source
tools for those jobs, so Jarvis looks them up instead of guessing.

There are 77 tools in it, researched on 2026-10-10. Each one records:
- what problem it solves, in plain words;
- its GitHub project;
- its licence (whether you may use it in a business);
- warnings: safety notes, paid parts, non-commercial voices;
- the pages the facts came from, and the date they were checked.

## Ask it

- **Ask Jarvis:** "How do I stop the model making things up?" or "What could give you a
  better memory?" He answers from the toolbox and says what is only claimed.
- **On the Jarvis screen:** click **Scout** and type what you need. "Already known" cards
  from the toolbox appear first, then Scout searches GitHub for more.
- **In the terminal:**
  ```bash
  bau toolbox ask "a voice for kids videos I can use commercially"
  bau toolbox list --category memory
  ```

## Claimed or checked?

Everything in the toolbox starts as a **claim**: what the project and its pages say about
it. To have BAU look at a tool for itself, run:

```bash
bau toolbox check "Kokoro"
```

Repo Scout then reads the tool's GitHub record, downloads it into a locked quarantine
folder (nothing in it is installed or run) and scans it. After that the toolbox shows
**inspected** with Scout's decision. Licence and security problems block a tool however
popular it is. Models on Hugging Face (like Hermes 4) aren't on GitHub; they are checked
with `bau models bench` instead.

## Licences to watch

Some popular voice tools may **not** be used in videos that earn money:
- **XTTS-v2 and F5-TTS:** their voices are licensed for non-commercial use only.
- **openWakeWord:** its ready-made wake-word models are non-commercial too.

Kokoro (Apache-2.0) and Chatterbox (MIT) can be used commercially. n8n is "fair-code":
internal use is fine, but offering it to others needs a licence.

## Keeping it fresh

Stars, versions and licences change. `bau toolbox validate` checks that every entry still
names its sources and makes no promises ("compliant", "guaranteed"). Re-checking each
tool is a job for a later session.
