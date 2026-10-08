"""Chat library: Claude and ChatGPT exports, imported and searched offline; Jarvis reads them
only as the owner's sharing choice allows."""

import json
import zipfile

import pytest

from bau.assistant import Assistant
from bau.audit import AuditLog
from bau.chats import ChatLibrary, parse
from bau.models.providers import ScriptedProvider

CLAUDE = [{
    "uuid": "c-1", "name": "Kids channel ideas", "created_at": "2026-05-01T10:00:00Z",
    "chat_messages": [
        {"sender": "human", "text": "Ideas for a counting song about ducks?",
         "created_at": "2026-05-01T10:00:00Z"},
        {"sender": "assistant", "text": "", "created_at": "2026-05-01T10:00:05Z",
         "content": [{"type": "text", "text": "Five little ducks counting backwards."},
                     {"type": "tool_use", "name": "x"}]},
    ]},
    {"uuid": "c-2", "name": "Empty", "created_at": "2026-05-02T10:00:00Z",
     "chat_messages": []}]

CHATGPT = [{
    "id": "g-1", "title": "Pricing plan", "create_time": 1767225600.0, "current_node": "n4",
    "mapping": {
        "n0": {"message": None, "parent": None},
        "n1": {"parent": "n0", "message": {"author": {"role": "system"},
               "content": {"content_type": "text", "parts": ["You are ChatGPT"]}}},
        "n2": {"parent": "n1", "message": {"author": {"role": "user"}, "create_time": 1.0,
               "content": {"content_type": "text", "parts": ["What should the "
                                                            "subscription cost?"]}}},
        "n3x": {"parent": "n2", "message": {"author": {"role": "assistant"},
                "content": {"parts": ["An edited-away answer about penguins."]}}},
        "n3": {"parent": "n2", "message": {"author": {"role": "assistant"},
               "content": {"parts": ["Start at nine dollars a month.",
                                     {"content_type": "image_asset_pointer"}]}}},
        "n4": {"parent": "n3", "message": {"author": {"role": "tool"},
               "content": {"parts": ["tool plumbing"]}}},
    }}]


def write_zip(path, name, data):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(name, json.dumps(data))
    return path


def jarvis(home, model=None, script=()):
    return Assistant(home, ScriptedProvider(script=list(script)), model or {}, "human:owner",
                     AuditLog(home / "audit" / "chain.jsonl", key=b""))


def test_both_exports_parse_to_the_threads_the_owner_saw():
    convs, skipped = parse(CLAUDE + CHATGPT + [{"something": "else"}])
    assert skipped == 1
    claude, empty, gpt = convs
    assert claude.messages[1] == ("assistant", "Five little ducks counting backwards.",
                                  "2026-05-01T10:00:05Z")
    assert empty.messages == []
    assert [m[:2] for m in gpt.messages] == [
        ("owner", "What should the subscription cost?"),
        ("assistant", "Start at nine dollars a month.")]          # no system, tool, branch
    assert gpt.created.startswith("2026-01-01")


def test_import_zips_search_read_and_reimport_without_doubles(tmp_path):
    lib = ChatLibrary(tmp_path)
    a = lib.import_file(write_zip(tmp_path / "claude.zip", "conversations.json", CLAUDE))
    b = lib.import_file(write_zip(tmp_path / "gpt.zip", "export/conversations.json", CHATGPT))
    assert a["conversations"]["claude"] == 2 and b["conversations"]["chatgpt"] == 1
    hits = lib.search("ducks counting")
    assert hits[0]["conversation"] == "claude/c-1" and "[ducks]" in hits[0]["excerpt"]
    assert lib.search("subscription price")[0]["title"] == "Pricing plan"   # any word
    assert lib.search("ducks", source="chatgpt") == []
    assert lib.search("penguins") == []                       # edited-away branch left out
    assert lib.search('"); DROP TABLE messages; --') == []     # odd input is only words
    conv = lib.conversation("chatgpt/g-1")
    assert [m["who"] for m in conv["messages"]] == ["owner", "assistant"]
    lib.import_file(tmp_path / "claude.zip")                  # same export again
    assert lib.stats()["by_source"]["claude"] == {"conversations": 2, "messages": 2,
                                                  "oldest": "2026-05-01",
                                                  "newest": "2026-05-02"}
    assert len(lib.search("ducks")) == 2                      # question + answer, once each
    with pytest.raises(KeyError):
        lib.conversation("claude/nope")


def test_a_zip_without_conversations_is_refused(tmp_path):
    with pytest.raises(ValueError, match="no conversations.json"):
        ChatLibrary(tmp_path).import_file(write_zip(tmp_path / "x.zip", "photo.json", {}))


def test_jarvis_on_a_cloud_model_waits_for_the_owners_choice(tmp_path):
    lib = ChatLibrary(tmp_path)
    lib.import_file(write_zip(tmp_path / "c.zip", "conversations.json", CLAUDE))
    cloud = jarvis(tmp_path, {"id": "glm-4.7-flash-zai", "deployment": "cloud"})
    out, err = cloud._run_tool("chat_search", {"query": "ducks"})
    assert err and "hasn't decided" in out["error"]
    lib.set_sharing("local-only")
    out, err = cloud._run_tool("chat_search", {"query": "ducks"})
    assert err and "keeps old chats away" in out["error"]
    local = jarvis(tmp_path, {"id": "glm-4.7-flash", "deployment": "local"})
    out, err = local._run_tool("chat_search", {"query": "ducks"})
    assert not err and out[0]["conversation"] == "claude/c-1"
    lib.set_sharing("cloud")
    out, err = cloud._run_tool("chat_read", {"conversation": "claude/c-1"})
    assert not err and out["title"] == "Kids channel ideas"
    assert jarvis(tmp_path, {})._run_tool("chat_search", {"query": "x"})[1] is False
    assert all(t.kind == "read" for n, t in cloud.tools.items() if n.startswith("chat_"))
    with pytest.raises(ValueError):
        lib.set_sharing("yes")


def test_old_chats_reach_the_model_as_untrusted_data(tmp_path):
    lib = ChatLibrary(tmp_path)
    lib.import_file(write_zip(tmp_path / "c.zip", "conversations.json", CLAUDE))
    lib.set_sharing("cloud")
    a = jarvis(tmp_path, {"deployment": "cloud"},
               [{"tool": "chat_search", "input": {"query": "ducks"}}, "Found it."])
    assert a.ask("What did I say about ducks?").text == "Found it."
    result = a.provider.calls[1]["messages"][-1]["content"][0]["content"]
    assert result.startswith("<untrusted_data") and "ducks" in result


def test_cli_import_search_and_sharing(tmp_path, monkeypatch, capsys):
    from bau import cli_ext
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    z = write_zip(tmp_path / "c.zip", "conversations.json", CLAUDE)

    class A:
        chats_cmd, files = "import", [str(z), str(tmp_path / "missing.zip")]
    assert cli_ext.cmd_chats(A()) == cli_ext.EXIT_BLOCKED       # one bad file, others kept
    out = json.loads(capsys.readouterr().out)
    assert out["imported"][0]["conversations"]["claude"] == 2 and "error" in out["imported"][1]

    class S:
        chats_cmd, choice = "sharing", None
    cli_ext.cmd_chats(S())
    assert "not decided" in json.loads(capsys.readouterr().out)["sharing"]
    S.choice = "local-only"
    cli_ext.cmd_chats(S())
    assert json.loads(capsys.readouterr().out)["sharing"] == "local-only"


def test_exports_are_never_committed():
    from pathlib import Path
    ignore = (Path(__file__).resolve().parents[1] / ".gitignore").read_text().split()
    assert "chat-exports/" in ignore and "conversations.json" in ignore
