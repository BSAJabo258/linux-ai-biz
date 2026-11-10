# Creator week workspace

An ICM workspace (folder structure as agent architecture). One run plans one week of posts
for the fictional adult virtual creator (docs/VIRTUAL-CREATOR.md). One agent (Jarvis, or a
coding agent in a terminal) walks it one stage at a time. The owner checks every stage
before the next one runs.

## Where things live

| Path | What |
|---|---|
| `CONTEXT.md` | the pipeline on one screen |
| `_shared/` | fixed for every week: persona, voice, platform rules |
| `setup/questionnaire.md` | fill the persona once, before the first week |
| `_templates/episode/` | the stamp every new week is copied from |
| `episodes/ep-NNN-slug/` | one folder per week: `brief.md` + `stages/01..04` |
| `_index/episodes.md` | generated list of weeks (never edit by hand) |

## Where to go

- **Start a week:** `bau ws episode creator-week "this week's theme"`
- **What's next:** `bau ws status creator-week`
- **Draft the next stage:** `bau ws run creator-week ep-NNN-slug`
- **Owner check, after reading and editing the output:** `bau ws check creator-week ep-NNN-slug NN`
- **Working one stage:** open `episodes/<ep>/stages/NN_*/CONTEXT.md` and load only what it lists.

## Rules

- Load only the files a stage's contract lists. Never the whole workspace.
- Write only into that stage's `output/` folder.
- Nothing in `_shared/` changes during a run; the owner edits it.
- The creator is a fictional adult: nothing may refer to minors (the `no_minors` check).
- Every post carries the AI disclosure. Explicit posts go to Fanvue only.
- Posting is never a stage here: the owner approves the finished week.
