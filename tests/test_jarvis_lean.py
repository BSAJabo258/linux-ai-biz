"""Jarvis, lean for a small model on the laptop (measured 2026-10-19 on Qwen2.5-1.5B with the
stick's llama.cpp: every question started with ~4,900 tokens - 3,155 of them the 34 tool
descriptions - and the model read for ~52 s before answering; one answer ran past 1,400
tokens; asked what tools it had, it searched GitHub, the search failed, and it said "we
don't have any" though its own toolbox had three).

So, for a local model: a few core tools in full plus a one-line menu of the rest
(tool_menu) and one way to run any of them (use_tool) - the same gateway, the same
owner-confirmation for consequential actions; the instructions stay the same during a
session so the model server's prompt cache is reused; answers are capped; and a failed
search never reads as "nothing exists". A hosted model keeps the full tool list.
Written before the code."""

from test_jarvis_live import MODEL, make
from test_scout import FakeGitHub

from bau import governor
from bau.assistant import CORE_TOOLS, LEAN_MAX_TOKENS, Assistant
from bau.audit import AuditLog
from bau.models.providers import ScriptedProvider

LOCAL = {"id": "qwen-local", "context": 16384, "deployment": "local"}


def lean(home, script, **clients):
    return Assistant(home, ScriptedProvider(list(script)), LOCAL, "human:owner",
                     AuditLog(home / "audit" / "chain.jsonl", key=b""), clients=clients)


def test_a_local_model_sees_a_short_menu_not_every_tool(tmp_path):
    a = lean(tmp_path, ["ok"])
    names = [t.name for t in a.specs()]
    assert set(names) == {*CORE_TOOLS, "tool_menu", "use_tool"}
    assert len(names) <= 10
    full = make(tmp_path, ["ok"])
    assert len(full.specs()) >= 30 and "use_tool" not in [t.name for t in full.specs()]
    size = sum(len(t.description) + len(str(t.input_schema)) for t in a.specs())
    assert size < sum(len(t.description) + len(str(t.input_schema)) for t in full.specs()) / 3


def test_the_menu_lists_every_other_tool_and_opens_one(tmp_path):
    a = lean(tmp_path, ["ok"])
    menu = a.t_tool_menu()
    listed = {line.split(":")[0] for line in menu["tools"]}
    assert listed == set(a.tools) - {*CORE_TOOLS, "tool_menu", "use_tool"}
    assert all(len(line) <= 140 for line in menu["tools"])
    one = a.t_tool_menu("money")
    assert one["name"] == "money" and "parameters" in one and "use_tool" in one["how"]


def test_use_tool_runs_the_real_tool_and_shows_its_card(tmp_path):
    a = lean(tmp_path, [{"tool": "use_tool", "input": {"name": "money", "input": {}}},
                        "Here is the money."])
    r = a.ask("how is the money?")
    assert r.text == "Here is the money." and r.cards[0]["tool"] == "money"
    assert "error" not in r.cards[0]["data"]


def test_use_tool_cannot_skip_the_owners_confirmation(tmp_path):
    governor.Governor(tmp_path, audit=AuditLog(tmp_path / "a.jsonl", key=b"")).hold("test")
    a = lean(tmp_path, [{"tool": "use_tool", "input": {"name": "release_hold", "input": {}}},
                        "Staged."])
    r = a.ask("release the hold")
    assert governor.hold_reason(tmp_path)                    # still on hold
    assert r.pending and r.pending[0]["tool"] == "release_hold"


def test_use_tool_refuses_unknown_and_itself(tmp_path):
    a = lean(tmp_path, ["ok"])
    assert "unknown tool" in a.t_use_tool("nope")["error"]
    assert "error" in a.t_use_tool("use_tool", {"name": "money"})
    assert "error" in a.t_use_tool("tool_menu")


def test_instructions_stay_the_same_during_a_session(tmp_path):
    a = lean(tmp_path, ["first", "second"])
    a.ask("hello")
    p1 = a.provider.calls[-1]["system"]
    a.ask("and again")
    assert a.provider.calls[-1]["system"] == p1   # the server's prompt cache stays valid


def test_a_local_model_gets_a_cap_on_answer_length(tmp_path):
    a = lean(tmp_path, ["ok"])
    a.ask("hi")
    assert a.provider.calls[-1]["max_tokens"] == LEAN_MAX_TOKENS <= 800
    full = make(tmp_path, ["ok"])
    full.ask("hi")
    assert full.provider.calls[-1]["max_tokens"] > LEAN_MAX_TOKENS


def test_a_failed_search_points_at_what_we_already_have(tmp_path):
    gh = FakeGitHub({"*": []}, fail={"*"})
    a = Assistant(tmp_path, ScriptedProvider([]), MODEL, "human:owner",
                  AuditLog(tmp_path / "audit" / "chain.jsonl", key=b""), clients={"github": gh})
    out = a.t_find_tools("stop the model making things up")
    assert out["found"] == 0
    assert out["already_researched"]                    # from the toolbox, offline
    assert "does not mean" in out["note"]


def test_a_local_model_gets_a_short_toolbox_answer(tmp_path):
    a = lean(tmp_path, ["ok"])
    r = a.t_toolbox("make decisions with a confidence score")
    assert len(r["answers"]) == 3
    assert set(r["answers"][0]) == {"name", "problem", "licence", "evidence"}
    full = make(tmp_path, ["ok"]).t_toolbox("make decisions with a confidence score")
    assert len(full["answers"]) == 5 and "sources" in full["answers"][0]


def test_saying_let_me_search_without_doing_it_gets_one_nudge(tmp_path):
    a = lean(tmp_path, ["Let me search the toolbox for that.",
                        {"tool": "toolbox", "input": {"question": "confidence"}},
                        "We already have Outlines, Instructor and Guidance."])
    r = a.ask("what do we have for confidence?")
    assert r.text.startswith("We already have") and r.cards[0]["tool"] == "toolbox"
    nudges = [m for m in a.messages if m.get("role") == "user"
              and "call the tool now" in str(m.get("content"))]
    assert len(nudges) == 1


def test_only_one_nudge_and_never_for_a_real_answer(tmp_path):
    a = lean(tmp_path, ["Let me check.", "Let me check again."])
    assert a.ask("anything?").text == "Let me check again."
    b = lean(tmp_path, ["You have three tools for that."])
    assert b.ask("q").text == "You have three tools for that." and len(b.provider.calls) == 1


def test_usage_comes_with_a_sentence_a_small_model_can_repeat(tmp_path):
    out = lean(tmp_path, ["ok"]).t_usage()
    assert out["say"].startswith("Today: ") and "$0.00" in out["say"]


def test_common_questions_get_their_facts_before_the_model_answers(tmp_path):
    a = lean(tmp_path, ["You spent nothing today."])
    r = a.ask("How much have the AI models cost today?")
    first = str(a.provider.calls[0]["messages"][-1]["content"])
    assert "Today: " in first and "<untrusted_data" in first      # facts, wrapped as data
    assert r.cards and r.cards[0]["tool"] == "usage_today"
    b = lean(tmp_path, ["All good."])
    b.ask("Is anything broken or waiting for me?")
    assert "overall" in str(b.provider.calls[0]["messages"][-1]["content"])
    c = lean(tmp_path, ["We have three."])
    c.ask("What tools do we already have for picking an answer?")
    assert "Outlines" in str(c.provider.calls[0]["messages"][-1]["content"])
    # Real model, 2026-10-27: "the Governor watchdog" got the toolbox, and "post the latest
    # video" got a kids-rule refusal without looking. Both now come with their facts.
    d = lean(tmp_path, ["Nothing needs you."])
    d.ask("What does the Governor watchdog say right now?")
    assert "overall" in str(d.provider.calls[0]["messages"][-1]["content"])
    e = lean(tmp_path, ["Nothing is queued."])
    r = e.ask("Post the latest video to TikTok now.")
    assert r.cards and r.cards[0]["tool"] == "publish_queue" and not r.pending


def test_facts_first_is_only_for_local_models_and_only_read_tools(tmp_path):
    full = make(tmp_path, ["ok"])
    full.ask("How much have the AI models cost today?")
    assert "Today: " not in str(full.provider.calls[0]["messages"][-1]["content"])
    from bau.assistant import GROUND
    a = lean(tmp_path, ["ok"])
    assert all(a.tools[name].kind == "read" for _, name, _ in GROUND)


def test_earlier_answers_are_not_carried_into_a_local_models_instructions(tmp_path):
    a = lean(tmp_path, ["The system is fine."])
    a.ask("status?")
    b = lean(tmp_path, ["ok"])
    b.ask("hi")
    assert "status?" in b.provider.calls[0]["system"]
    assert "The system is fine." not in b.provider.calls[0]["system"]


# Real run, 2026-11-01 (Qwen3.5-4B, llama.cpp b11747, fresh home): told "Remember that the
# creator posts at 7pm", it was handed recall's facts, searched twice, saved nothing and said
# "I've saved that". A command to remember is not a question about the past.
def test_a_remember_command_is_not_answered_with_recall(tmp_path):
    a = lean(tmp_path, ["Saved."])
    r = a.ask("Remember that the creator posts on Instagram every day at 7pm.")
    assert "Facts already looked up" not in str(a.provider.calls[0]["messages"][-1]["content"])
    assert r.cards[0]["tool"] == "remember"


# Real-model check, 2026-11-01 (second run): asked to remember, the model searched instead and
# said "I'm adding that". A small model is not trusted with it: the note is saved first.
def test_a_remember_command_is_saved_before_the_model_answers(tmp_path):
    a = lean(tmp_path, ["Got it."])
    r = a.ask("Jarvis, remember that the creator posts on Instagram every day at 7pm.")
    notes = list((tmp_path / "memory" / "records").glob("*.md"))
    assert len(notes) == 1 and "every day at 7pm" in notes[0].read_text()
    assert "Already saved" in str(a.provider.calls[0]["messages"][-1]["content"])
    assert r.cards[0]["tool"] == "remember" and r.text == "Got it."
    b = lean(tmp_path, ["We said 7pm."])
    b.ask("Do you remember when the creator posts?")
    # a question saves nothing
    assert len(list((tmp_path / "memory" / "records").glob("*.md"))) == 1
    b = lean(tmp_path, ["We said 7pm."])
    b.ask("Do you remember what we decided about posting?")
    assert "Facts already looked up" in str(b.provider.calls[0]["messages"][-1]["content"])


# Same run: "What workspaces do I have?" - the menu line for workspaces was cut at "e.g" and
# the model never found it.
def test_menu_lines_are_not_cut_at_an_abbreviation(tmp_path):
    lines = lean(tmp_path, ["ok"]).t_tool_menu()["tools"]
    ws = next(x for x in lines if x.startswith("workspaces:"))
    assert "creator week" in ws
    a = lean(tmp_path, ["You have none yet."])
    r = a.ask("What workspaces do I have?")
    assert r.cards and r.cards[0]["tool"] == "workspaces"


# Same run: with no limits set, the model said "4 calls remaining before today's limit".
def test_usage_says_plainly_when_no_limit_is_set(tmp_path):
    assert "No daily limits are set." in lean(tmp_path, ["ok"]).t_usage()["say"]


# Same run: asked to plan the creator's posts, it never saw creator_batch (menu only).
def test_the_creator_batch_is_in_a_small_models_core_tools(tmp_path):
    assert "creator_batch" in CORE_TOOLS
