# Creator week pipeline

One run = one week of posts. Each stage reads the previous stage's output and writes its
own. The owner reads, edits and checks each output before the next stage runs.

| Stage | Job | Writes | Owner checks |
|---|---|---|---|
| 01_plan | the week's posts: day, platform, tier, idea | `plan.md` | right mix; explicit only on Fanvue |
| 02_captions | one caption per post, with the AI disclosure | `captions.md` | in the persona's voice; nothing flagged |
| 03_prompts | one image or video prompt per post | `prompts.md` | the persona looks the same in every prompt |
| 04_review | you make the media and approve the week | `review.md` | every post seen; the week approved |

Status is read from the files: a stage is done when its output exists and its
`output/.checked` matches the output (edit it after checking and the check is void).

The `no_minors` check runs on the stages that list it. A stage can't be checked while it
finds a problem: fix the file, then check again.
