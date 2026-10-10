# Series engine: the same characters in every clip

AI video models forget. Ask for "Pip the hedgehog" twice and you can get two different
hedgehogs. The series engine fixes that for your kids channel: you describe each character
and the channel's look **once**, and every clip prompt then describes them **word for
word the same way**.

## 1. Fill in the sheets (once)

In your kids workspace (`bau ws create kids-channel` made it), open the `_shared` folder:

- **`characters/main-character.yaml`** - your star. Fill in every `{{...}}`:
  - what they are;
  - three things a child would recognise them by;
  - what they always wear;
  - their colours, personality and voice;
  - their catchphrase;
  - what they are **never** shown as.

  Copy the file (for example `friend.yaml`) for each other main character and set
  `role: friend`.
- **`style.yaml`** - the look of the whole show: art style, colours, light, camera, the
  shape of the video (16:9 for YouTube, 9:16 for Shorts) and what to avoid.

Then check them:

```bash
bau series check kids-channel
```

It refuses sheets with blanks left, too little description to keep a character
recognisable, or a name that belongs to another company (Peppa Pig, Bluey...).

## 2. Plan an episode

```bash
bau ws episode kids-channel "Pip learns to share berries"
bau series formats
bau series plan kids-channel ep-001 --format problem-song-solution --seconds 60
```

The plan splits the episode into clips of 3 to 15 seconds (what the studio's video model
makes), each with a ready prompt. It is saved as `series-plan.md` in the episode folder,
where the storyboard and video-prompt steps build on it. The formats are common story
shapes for young children:

| Format | Shape |
|---|---|
| `problem-song-solution` | a small problem, a try, a friend helps, a fix, a short song |
| `count-along` | counting slowly with pauses for the child |
| `question-reveal` | a question, guesses, clues, the answer |
| `call-and-response` | a line, a pause, the child says it back |

They are storytelling shapes, not promises about views: watch your own channel's numbers
and change formats often.

## 3. One clip prompt at a time

```bash
bau series prompt kids-channel "Pip finds a lost acorn under a leaf" --cast pip
```

Or ask Jarvis: "Give me a clip prompt for Pip finding an acorn". Take the prompt to the
studio (`bau video quote "..."`, docs/STUDIO.md): it is priced first and made only when
you confirm.

## What it checks for you

- **Drift.** The video-prompt step (`04_video-prompts`) is checked before you can tick it.
  A character shown in a colour that isn't on their sheet ("Pip in a red scarf"), shown
  as something on their "never" list, or named without their description is flagged.
- **Kids rules.** A scene with anything frightening or unsuitable is refused, as
  everywhere else in BAU.
- **Sameness.** YouTube stops paying channels that look mass-produced from one template.
  The plan warns you when the same format is used four episodes in a row, or when a new
  idea is almost the same as an earlier one. Consistent characters, fresh episodes.
