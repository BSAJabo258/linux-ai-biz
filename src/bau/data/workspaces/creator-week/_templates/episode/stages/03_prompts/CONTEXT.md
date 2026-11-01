# 03_prompts: one image or video prompt per post

One job: write the generation prompt for every post's image or short video.

## Inputs
- Working (this run): ../01_plan/output/plan.md
- Working (this run): ../02_captions/output/captions.md
- Reference (every run): ../../../../_shared/persona.md

## Process
1. One prompt per post, in the plan's order.
2. Start every prompt with the persona's fixed look, word for word, so she looks the same.
3. Describe the scene, outfit, light and framing. Clearly adult; never youth-coded.

## Outputs
- prompts.md → output/

## Checks
- no_minors

## Brain
small (the free local model: a routine step)

## Human check
Does every prompt start with the same look? Is everything clearly adult?
