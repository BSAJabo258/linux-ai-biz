"""Chat library: the owner's exported Claude and ChatGPT conversations, searchable offline.

Where the exports come from (checked 2026-10-07):

* Claude: Settings > Privacy > Export data. A download link arrives by email and expires
  after 24 hours (support.claude.com, "Export your Claude data", updated 2026-07-08). The
  ZIP holds ``conversations.json``.
* ChatGPT: Settings > Data controls > Export data. A download link arrives by email; the
  ZIP holds ``conversations.json`` (help.openai.com refused scripted reads on 2026-10-07, so
  these steps come from the app, not the help page).

Neither company documents the file layout. What this module reads:

* Claude: a list of ``{uuid, name, created_at, chat_messages: [{sender: human|assistant,
  text | content: [{type: text, text}], created_at}]}``.
* ChatGPT: a list of ``{id | conversation_id, title, create_time, current_node, mapping:
  {node_id: {message: {author: {role}, content: {parts | text}, create_time}, parent}}}``.
  The thread the owner saw is the walk from ``current_node`` back through ``parent``;
  edited-away branches are left out.

Anything else is counted as skipped and reported, never guessed at.

Everything stays in ``BAU_HOME/chats/chats.db`` (SQLite full-text search, stdlib). Old chats
are personal data. Jarvis's chat tools send excerpts to whatever model he runs on, so for a
cloud model the owner decides once with ``bau chats sharing``; until then Jarvis can't
read them. Excerpts reach the model as untrusted data, like every tool result.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import re
import sqlite3
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .home import bau_home
from .store import YamlStore

SOURCES = ("claude", "chatgpt")
SHARING = ("cloud", "local-only")


@dataclass
class Conversation:
    source: str
    cid: str
    title: str
    created: str
    messages: list[tuple[str, str, str]] = field(default_factory=list)  # role, text, ts


def _iso(value: Any) -> str:
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value, dt.UTC).isoformat()
    return str(value or "")


def _claude(c: dict[str, Any]) -> Conversation | None:
    if not c.get("uuid"):
        return None
    msgs = []
    for m in c.get("chat_messages") or []:
        text = m.get("text") or "\n".join(
            b.get("text", "") for b in m.get("content") or []
            if isinstance(b, dict) and b.get("type") == "text")
        if text.strip():
            role = "owner" if m.get("sender") == "human" else "assistant"
            msgs.append((role, text.strip(), _iso(m.get("created_at"))))
    return Conversation("claude", str(c["uuid"]), c.get("name") or "(untitled)",
                        _iso(c.get("created_at")), msgs)


def _chatgpt(c: dict[str, Any]) -> Conversation | None:
    mapping = c.get("mapping") or {}
    cid = c.get("conversation_id") or c.get("id")
    if not cid or not isinstance(mapping, dict):
        return None
    chain, node, seen = [], c.get("current_node"), set()
    while node in mapping and node not in seen:       # the thread the owner saw
        seen.add(node)
        chain.append(mapping[node])
        node = mapping[node].get("parent")
    nodes = chain[::-1] or list(mapping.values())
    msgs = []
    for n in nodes:
        m = n.get("message") or {}
        role = (m.get("author") or {}).get("role")
        if role not in ("user", "assistant"):
            continue                                  # system prompts, tool plumbing
        content = m.get("content") or {}
        parts = content.get("parts") or [content.get("text", "")]
        text = "\n".join(p if isinstance(p, str) else p.get("text", "")
                         for p in parts if isinstance(p, (str, dict)))
        if text.strip():
            msgs.append(("owner" if role == "user" else "assistant", text.strip(),
                         _iso(m.get("create_time"))))
    return Conversation("chatgpt", str(cid), c.get("title") or "(untitled)",
                        _iso(c.get("create_time")), msgs)


def parse(data: Any) -> tuple[list[Conversation], int]:
    """Conversations from a ``conversations.json`` of either service, and how many items
    had a shape this module doesn't know."""
    convs, skipped = [], 0
    for item in data if isinstance(data, list) else []:
        conv = None
        if isinstance(item, dict) and "chat_messages" in item:
            conv = _claude(item)
        elif isinstance(item, dict) and "mapping" in item:
            conv = _chatgpt(item)
        if conv is None:
            skipped += 1
        else:
            convs.append(conv)
    if not isinstance(data, list):
        skipped += 1
    return convs, skipped


def read_export(path: Path) -> Any:
    """The JSON inside an export: a ZIP (read in memory, nothing extracted) or the bare
    ``conversations.json``."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.rsplit("/", 1)[-1] == "conversations.json"]
            if not names:
                raise ValueError(f"{path.name} has no conversations.json - is it a Claude "
                                 "or ChatGPT export?")
            return json.loads(z.read(min(names, key=len)))
    return json.loads(path.read_text(encoding="utf-8"))


def _match(query: str, any_word: bool = False) -> str:
    words = re.findall(r"\w+", query)
    return (" OR " if any_word else " ").join('"' + w.replace('"', '""') + '"' for w in words)


class ChatLibrary:
    def __init__(self, home: Path | None = None):
        self.home = home or bau_home()
        self.dir = self.home / "chats"
        self.db_path = self.dir / "chats.db"

    @contextlib.contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        """One transaction: committed when the block ends, rolled back on error."""
        self.dir.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.db_path)
        try:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    source TEXT, cid TEXT, title TEXT, created TEXT, n INTEGER,
                    PRIMARY KEY (source, cid));
                CREATE VIRTUAL TABLE IF NOT EXISTS messages USING fts5(
                    text, title, source UNINDEXED, cid UNINDEXED, role UNINDEXED,
                    ts UNINDEXED, seq UNINDEXED, tokenize = 'porter unicode61');
            """)
            with db:
                yield db
        finally:
            db.close()

    # ------------------------------------------------------------ write
    def import_file(self, path: Path) -> dict[str, Any]:
        """Add or refresh every conversation in an export. Importing the same or a newer
        export again replaces those conversations instead of doubling them."""
        convs, skipped = parse(read_export(path))
        counts = {s: 0 for s in SOURCES}
        n_msgs = 0
        with self._db() as db:
            for c in convs:
                db.execute("DELETE FROM messages WHERE source = ? AND cid = ?",
                           (c.source, c.cid))
                db.execute("INSERT OR REPLACE INTO conversations VALUES (?, ?, ?, ?, ?)",
                           (c.source, c.cid, c.title, c.created, len(c.messages)))
                db.executemany(
                    "INSERT INTO messages (text, title, source, cid, role, ts, seq) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [(t, c.title, c.source, c.cid, r, ts, i)
                     for i, (r, t, ts) in enumerate(c.messages)])
                counts[c.source] += 1
                n_msgs += len(c.messages)
        return {"file": path.name, "conversations": counts, "messages": n_msgs,
                "skipped": skipped}

    # ------------------------------------------------------------ read
    def search(self, query: str, k: int = 10, source: str | None = None
               ) -> list[dict[str, Any]]:
        """Best-matching messages, every word first; any word when that finds nothing."""
        if not self.db_path.exists() or not _match(query):
            return []
        sql = ("SELECT source, cid, title, role, ts, "
               "snippet(messages, 0, '[', ']', ' ... ', 30) FROM messages "
               "WHERE messages MATCH ?" + (" AND source = ?" if source else "")
               + " ORDER BY rank LIMIT ?")
        with self._db() as db:
            for any_word in (False, True):
                args = [_match(query, any_word)] + ([source] if source else []) + [k]
                rows = db.execute(sql, args).fetchall()
                if rows:
                    break
        return [{"conversation": f"{s}/{c}", "title": t, "who": r, "when": ts[:10],
                 "excerpt": snip} for s, c, t, r, ts, snip in rows]

    def conversation(self, ref: str, max_chars: int = 12000) -> dict[str, Any]:
        source, _, cid = ref.partition("/")
        with self._db() as db:
            head = db.execute("SELECT title, created FROM conversations "
                              "WHERE source = ? AND cid = ?", (source, cid)).fetchone()
            if head is None:
                raise KeyError(f"no conversation {ref} (search first; refs look like "
                               "claude/<id> or chatgpt/<id>)")
            rows = db.execute("SELECT role, text FROM messages WHERE source = ? AND cid = ? "
                              "ORDER BY CAST(seq AS INTEGER)", (source, cid)).fetchall()
        out, used = [], 0
        for role, text in rows:
            if used + len(text) > max_chars:
                out.append({"who": "note", "text": "(rest cut to keep this short)"})
                break
            out.append({"who": role, "text": text})
            used += len(text)
        return {"conversation": ref, "title": head[0], "when": head[1][:10], "messages": out}

    def stats(self) -> dict[str, Any]:
        if not self.db_path.exists():
            return {"conversations": 0, "note": "nothing imported yet: bau chats import FILE"}
        with self._db() as db:
            rows = db.execute("SELECT source, COUNT(*), SUM(n), MIN(created), MAX(created) "
                              "FROM conversations GROUP BY source").fetchall()
        return {"conversations": sum(r[1] for r in rows),
                "by_source": {s: {"conversations": n, "messages": m or 0,
                                  "oldest": (lo or "")[:10], "newest": (hi or "")[:10]}
                              for s, n, m, lo, hi in rows},
                "sharing": self.sharing()}

    # ------------------------------------------------------------ owner's choice
    def sharing(self) -> str | None:
        """'cloud', 'local-only', or None while the owner hasn't decided."""
        return (YamlStore(self.home / "config" / "chats.yaml").load() or {}).get("sharing")

    def set_sharing(self, value: str) -> None:
        if value not in SHARING:
            raise ValueError(f"sharing must be one of {SHARING}")
        (self.home / "config").mkdir(parents=True, exist_ok=True)
        YamlStore(self.home / "config" / "chats.yaml").save({"sharing": value})
