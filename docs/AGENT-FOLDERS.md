# Agents as folders

In BAU an **agent is a folder, not a model**. The folder holds the agent's instructions,
its skills, which tools it may use, and which brain thinks for it. The thinking comes from
the brains you already chose (`bau ws brains`): the free small model for routine work,
Claude for judgement. You change an agent by editing text files, not by training or
downloading anything.

```
researcher/
  AGENT.md                    who it is, what it does, its brain, tools and skills
  skills/
    cite-sources/SKILL.md     a skill: know-how it opens when it needs it
    ask-before-guessing/SKILL.md
```

BAU ships two agents to start with:

| Agent | Brain | What it does |
|---|---|---|
| `researcher` | strong (Claude) | researches a question; every fact gets a source and a date; saves a draft report |
| `producer` | small (free local model) | writes short business copy in plain words; saves drafts for you |

## Use them

```bash
bau agents list                         # every agent and whether you approved it
bau agents show researcher              # its brain, tools, skills and any problems
bau agents approve researcher           # you: approve it as it is now
bau agents run researcher "Which mug suppliers ship to Ohio in under a week?"
```

Or ask Jarvis: "ask the researcher which mug suppliers ship fast". Jarvis can only ask an
agent you approved.

## Make your own

Start from one of the shipped agents:

```bash
bau agents new listing-writer --from producer
```

It prints the new folder (in BAU's home, `/var/lib/bau/agents/` on the laptop). An agent
of yours with the same name as a shipped one replaces it. Then edit its `AGENT.md`:

```markdown
---
name: listing-writer            # lowercase and hyphens, same as the folder name
description: Writes product listings for the shop from the product notes.
brain: small                    # small, strong, or content (content gets no tools)
tools: [memory.brain, artifact.write_draft]
skills: [plain-words]           # shared skills it uses (its own skills/ load anyway)
max_steps: 6
---
# Listing writer

What it should do, step by step, in plain words.
```

Then `bau agents approve listing-writer`.

## Skills

A skill is a folder with a `SKILL.md`: a short `name`, a `description` saying what it is
for and when to use it, then the know-how. This is the open **Agent Skills** format that
Claude, ChatGPT/Codex, GitHub Copilot, Cursor and many other tools also read, so skills
other people publish work here too.

Only each skill's name and description are given to the agent at the start. The agent
opens the full skill when it needs it. That keeps the agent fast and cheap, however many
skills it has.

Bring in a skill you downloaded (for example from Anthropic's skills collection or the
Awesome Agent Skills list):

```bash
bau agents add-skill ~/Downloads/some-skill
```

It is copied **as text only**: `SKILL.md` and its `.md`/`.txt` reference files. Any
scripts in it are listed but never copied or run. Check its licence: some published
skills are not free for business use.

## What protects you

- **You approve each agent, as it is.** The approval is tied to the exact files. Change
  `AGENT.md` or any of its skills, and the agent stops until you approve it again. Jarvis
  and agents can never approve.
- **Only the tools it lists.** Every tool call goes through BAU's gateway, which refuses
  anything not in `tools:`. Agents save drafts; they never post, pay or send.
- **Skills and tool results are data.** What an agent reads, a skill included, reaches the
  model marked as data, so instructions hidden in a downloaded skill or a web page are not
  obeyed.
- **The content brain stays sealed.** An agent with `brain: content` gets no tools and no
  MCP servers, and never runs in a kids workspace.
- **Recorded:** every approval and every run is in the audit log.
