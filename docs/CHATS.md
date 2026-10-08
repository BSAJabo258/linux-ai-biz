# Your old chats: Claude and ChatGPT in one searchable library

BAU can load every conversation you've had with Claude and ChatGPT. Then you, or Jarvis,
can search them all at once: "what did I decide about pricing?", "find the duck song
ideas".

Everything stays in your BAU folder (`chats/chats.db`). Nothing is uploaded anywhere by
loading or searching.

## 1. Download your chats (once per service)

**Claude:** on claude.ai (web or desktop app, not the phone app): your initials, bottom
left > **Settings** > **Privacy** > **Export data**. A download link arrives by email.
Download it within 24 hours: it's a ZIP file.

**ChatGPT:** on chatgpt.com: your picture > **Settings** > **Data controls** >
**Export data** > **Confirm export**. A download link arrives by email. Download the ZIP.

You don't need to unzip either file.

## 2. Put the ZIPs where BAU can read them

**In a codespace:** in the file list on the left, right-click the empty space > **New
Folder** and name it `chat-exports`. Drag both ZIP files from your computer into that
folder. (`chat-exports` is on the never-commit list, so your chats can't end up on GitHub.)

**On the laptop:** copy them anywhere in your home folder, for example `~/chat-exports`.

## 3. Load them

```bash
bau chats import chat-exports/*.zip
```

It says how many conversations and messages it loaded from each service. A later export
can be imported the same way: conversations already loaded are refreshed, not doubled.

## 4. Search them yourself

```bash
bau chats search "pricing plan"
```

Each result shows a reference such as `claude/1a2b...`. To read that whole conversation:

```bash
bau chats show claude/1a2b...
```

To see what is loaded:

```bash
bau chats stats
```

## 5. Let Jarvis search them (your choice)

Jarvis sends the bits he finds to the model he runs on. In the codespace that's Z.ai's
cloud service (a company in Singapore); on the laptop with a local model, nothing leaves
the machine. So for a cloud model **you decide**, once:

```bash
bau chats sharing cloud
```

lets Jarvis read your chats on any model, cloud included.

```bash
bau chats sharing local-only
```

lets him read them only on a model running on your own machine.

Until you choose, Jarvis on a cloud model tells you he can't read them yet. Then ask him:
"search my old chats for the kids channel ideas" or "what did I ask ChatGPT about
pricing?".

Old chats are treated as information, never as instructions. If an old message says
"do X", Jarvis won't do it because of that.

## When you're done

The ZIP files hold all your chats. Once imported, you can delete them from
`chat-exports`; the library keeps its own copy. To remove the library itself, delete
`chats/` in your BAU folder (in a codespace: `/workspaces/.bau-home/chats`).
