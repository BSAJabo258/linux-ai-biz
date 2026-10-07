# Kids channel pipeline

One run = one episode. Each stage reads the previous stage's output and writes its own.
The owner reads, edits and checks each output before the next stage runs.

| Stage | Job | Writes | Owner checks |
|---|---|---|---|
| 01_pitch | one new story with one learning goal | `pitch.md` | different from earlier episodes |
| 02_script | the narration and dialogue | `script.md` | read aloud: calm, age-right, no flagged words |
| 03_storyboard | scene by scene | `storyboard.md` | every script line has a scene |
| 04_video-prompts | one video-generator prompt per scene | `video-prompts.md` | characters look the same in every prompt |
| 05_metadata | title, description, tags | `metadata.md` | plain title, no links or calls to action |
| 06_review | you make the video and watch it | `review.md` | watched end to end; made for kids |

Status is read from the files: a stage is done when its output exists and its
`output/.checked` matches the output (edit it after checking and the check is void).

Kids checks (`kids_text`, `kids_metadata`) run on the stages that list them. A stage
can't be checked while they find a problem: fix the file, then check again.
