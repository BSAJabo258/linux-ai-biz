"""Jarvis may use every approved model at will: list them, switch this conversation, or
ask one model a question without switching. Approval stays the owner's typed command."""

import pytest

from bau.assistant import MODEL_CMD, Assistant, pick_model
from bau.audit import AuditLog
from bau.localonly import set_mode
from bau.models.providers import ScriptedProvider
from bau.registry import CapabilityRegistry
from bau.runtime import seed_registry


def home_with_model(tmp_path, monkeypatch):
    seed_registry(tmp_path)
    reg = CapabilityRegistry(tmp_path / "registry" / "capabilities.yaml")
    rec = reg.data["model"]["qwen3.5-4b"]
    rec.update(status="APPROVED", benchmark={"reply_ok": True})
    reg.save()
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    set_mode(tmp_path, "cloud", "human:owner")
    monkeypatch.setenv("ZAI_API_KEY", "x")
    return tmp_path


def make(home):
    return Assistant(home, ScriptedProvider(["ok"]),
                     {"id": "qwen3.5-9b", "deployment": "local", "context": 8192},
                     "human:owner", AuditLog(home / "audit" / "chain.jsonl", key=b""))


def test_model_commands_do_not_swallow_ordinary_words():
    assert MODEL_CMD.match("model").group(1) == ""
    assert MODEL_CMD.match("model qwen3.5-4b").group(1) == "qwen3.5-4b"
    assert MODEL_CMD.match("switch model to qwen3.5-4b").group(1) == "qwen3.5-4b"
    assert MODEL_CMD.match("models are useful") is None


def test_the_owner_can_list_and_switch_without_a_model_tool(tmp_path, monkeypatch):
    home = home_with_model(tmp_path, monkeypatch)
    seen = []

    def provider_for(mid, h):
        seen.append(mid)
        return ScriptedProvider(["switched"]), {"deployment": "local", "id": mid}

    monkeypatch.setattr("bau.runtime.provider_for", provider_for)
    a = make(home)
    listed = a.t_models("list")
    assert listed["current"] == "qwen3.5-9b" and "qwen3.5-4b" in listed["usable"]
    reply = a.ask("model qwen3.5-4b")
    assert "Switched to qwen3.5-4b" in reply.text
    assert a.model["id"] == "qwen3.5-4b" and a.messages == [] and seen == ["qwen3.5-4b"]


def test_a_model_can_ask_another_without_switching(tmp_path, monkeypatch):
    home = home_with_model(tmp_path, monkeypatch)
    fake = ScriptedProvider(["the other model says hi"])

    def provider_for(mid, h):
        return fake, {"deployment": "local", "id": mid}

    monkeypatch.setattr("bau.runtime.provider_for", provider_for)
    a = make(home)
    out = a.t_models("ask", model="qwen3.5-4b", question="hi")
    assert out["model"] == "qwen3.5-4b" and "says hi" in out["answer"]
    assert a.model["id"] == "qwen3.5-9b"           # Jarvis's own model is unchanged
    assert fake.calls[-1]["tools"] == []


def test_a_tool_switch_waits_for_the_next_owner_message(tmp_path, monkeypatch):
    home = home_with_model(tmp_path, monkeypatch)
    monkeypatch.setattr("bau.runtime.provider_for",
                        lambda mid, h: (ScriptedProvider(["next"]),
                                        {"deployment": "local", "id": mid}))
    a = make(home)
    out = a.t_models("use", model="qwen3.5-4b")
    assert out["next"] == "qwen3.5-4b" and a.model["id"] == "qwen3.5-9b"
    a.ask("hello")
    assert a.model["id"] == "qwen3.5-4b"


def test_unapproved_and_content_lane_models_are_not_usable(tmp_path, monkeypatch):
    home = home_with_model(tmp_path, monkeypatch)
    reg = CapabilityRegistry(home / "registry" / "capabilities.yaml")
    reg.data["model"]["qwen3.5-4b"]["status"] = "REGISTERED"
    reg.data["model"]["qwen3-4b-heretic-content"]["status"] = "APPROVED"
    reg.save()
    a = make(home)
    rows = {r["model"]: r for r in a._model_rows()}
    assert rows["qwen3.5-4b"]["usable"] is False
    assert "approve it first" in rows["qwen3.5-4b"]["why"]
    assert rows["qwen3-4b-heretic-content"]["usable"] is False
    with pytest.raises(ValueError, match="content-lane"):
        a.switch_model("qwen3-4b-heretic-content")


def test_pick_model_includes_a_newly_approved_model_as_a_backup(tmp_path, monkeypatch):
    home = home_with_model(tmp_path, monkeypatch)
    reg = CapabilityRegistry(home / "registry" / "capabilities.yaml")
    extra = dict(reg.data["model"]["glm-4.7-flash-zai"], model_id="extra-cloud",
                 name="Another hosted model", status="APPROVED",
                 commercial_use=True, api_key_env="EXTRA_KEY")
    reg.add("model", extra)
    monkeypatch.setenv("EXTRA_KEY", "x")
    _, rec = pick_model(home)
    assert rec["id"] == "extra-cloud"           # newly approved, not hardcoded in order
    assert "qwen3.5-4b" in rec["fallbacks"]     # the local model still backs it up
