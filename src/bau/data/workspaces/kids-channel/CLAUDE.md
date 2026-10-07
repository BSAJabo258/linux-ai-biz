# Kids channel workspace

An ICM workspace (folder structure as agent architecture). It makes original episodes for a
faceless YouTube kids channel, made for kids. One agent (Jarvis, or Claude in VS Code)
walks it one stage at a time. The owner checks every stage before the next one runs.

## Where things live

| Path | What |
|---|---|
| `CONTEXT.md` | the pipeline on one screen |
| `_shared/` | fixed for every episode: series bible, voice, kids rules |
| `setup/questionnaire.md` | fill the series bible once, before the first episode |
| `_templates/episode/` | the stamp every new episode is copied from |
| `episodes/ep-NNN-slug/` | one folder per episode: `brief.md` + `stages/01..06` |
| `_index/episodes.md` | generated list of episodes (never edit by hand) |

## Where to go

- **Start an episode:** `bau ws episode kids-channel "your idea"`
- **What's next:** `bau ws status kids-channel`
- **Draft the next stage:** `bau ws run kids-channel ep-NNN-slug`
- **Owner check, after reading and editing the output:** `bau ws check kids-channel ep-NNN-slug NN`
- **Working one stage:** open `episodes/<ep>/stages/NN_*/CONTEXT.md` and load only what it lists.

## Rules

- Load only the files a stage's contract lists. Never the whole workspace.
- Write only into that stage's `output/` folder.
- Nothing in `_shared/` changes during a run; the owner edits it.
- Publishing is never a stage here. The owner queues the finished video with
  `bau youtube add ... --kids` and confirms it in `bau youtube review`.
