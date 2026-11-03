# Setup steps pop up in Jarvis

Your ask (2026-11-02): a pop-up with an Accept button for everything still waiting on you,
so the work can carry on.

When you open Jarvis, every setup step that is not done on this computer pops up by itself,
one at a time. Each card says what the step does. Press **Accept** to run it, or **Not now**
to skip it for this time. A step that is done does not come back.

| Step | What Accept does |
|---|---|
| Use your API keys while online | Opens a terminal that switches on the hosted models your keys pay for (`bau set-status model ... APPROVED`). After that, Jarvis answers with them first while you're online and with the local model when you're offline. Shown only when a key is on this computer and its model is still off. NVIDIA's free API is a trial: their terms say business use needs a paid plan |
| Bring in the current rules | Swaps in the rules that came with your newest BAU (creator, Michigan, Fanvue). The old copy is kept beside it as `regulations.before-DATE` |
| Install NVIDIA's driver | Opens a terminal running `sudo bau-gpu-setup`. Type your password there, then restart when it says |
| Set up pictures on this computer | Opens a terminal running the pictures setup (about 10 GB download, once). It shows up only after NVIDIA's driver works |
| Set up private web search | Opens a terminal running the search setup |
| Turn on nightly updates | Opens a terminal running `sudo bau update auto` |
| Let Jarvis work on his own | Opens a terminal that switches on the autopilot timer (docs/AUTOPILOT.md) |
| Set your Fanvue prices | Opens a terminal that asks you for each price. Nothing is filled in for you |

You can also say or type **"do all"**, **"let's do it all"**, **"continue"** or **"what's
waiting on me?"**. Jarvis then puts every card that is waiting for you on screen at once,
without asking the AI model. That takes a second, even on the small model.

Steps that need your password always open a terminal, so you see the exact command and type
the password yourself. Nothing runs without your Accept. Jarvis and the AI models cannot
start these steps themselves.

Not in the pop-ups:

- **A lawyer's or accountant's sign-off.** Only those people can give it (`bau reg promote`).
- **Your explicit limits for levels 2 and 3** (`explicit_boundaries`). You write those
  yourself in Aria's profile.

Built and tested 2026-11-02:

- In a real browser on a test computer, the card popped up, Accept brought in the rules,
  and the next step came up.
- The terminal steps were faked in that run. They have not run on your desktop yet.
