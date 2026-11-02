"""Online, Jarvis thinks with the owner's API keys; offline, with the local model (the owner,
2026-11-02: "the local model is to be able to use with no Internet connection ... otherwise it
should be using also my API key"). The keys' hosted models answer first while the internet is
up, the local model last as the backup; offline only the local model is asked, so there is
no wait on a model that cannot answer. Fakes only. Written before the code."""

import pytest

from bau import network
from bau.assistant import pick_model
from bau.registry import CapabilityRegistry
from bau.runtime import seed_registry


@pytest.fixture
def home(isolated_home, monkeypatch):
    seed_registry(isolated_home)
    reg = CapabilityRegistry(isolated_home / "registry" / "capabilities.yaml")
    for mid in ("nemotron-3-super-nim", "glm-4.7-flash-zai", "qwen3.5-4b"):
        reg.data["model"][mid]["status"] = "APPROVED"
    reg.data["model"]["qwen3.5-4b"]["benchmark"] = {"reply_ok": True}
    reg.save()
    monkeypatch.setenv("NVIDIA_API_KEY", "x")
    monkeypatch.setenv("ZAI_API_KEY", "x")
    return isolated_home


def _online(monkeypatch, up):
    monkeypatch.setattr(network, "detect", lambda: network.NetworkFacts(online=up, wired=True))


def test_online_the_api_keys_answer_first_and_the_local_model_is_the_backup(home, monkeypatch):
    _online(monkeypatch, True)
    provider, rec = pick_model(home)
    assert rec["id"] == "glm-4.7-flash-zai"
    assert rec["fallbacks"] == ["nemotron-3-super-nim", "qwen3.5-4b"]
    assert provider.names == ["glm-4.7-flash-zai", "nemotron-3-super-nim", "qwen3.5-4b"]


def test_offline_only_the_local_model_is_asked(home, monkeypatch):
    _online(monkeypatch, False)
    provider, rec = pick_model(home)
    assert rec["id"] == "qwen3.5-4b" and not rec.get("fallbacks")


def test_a_model_whose_key_is_missing_is_left_out(home, monkeypatch):
    _online(monkeypatch, True)
    monkeypatch.delenv("ZAI_API_KEY")
    _, rec = pick_model(home)
    assert rec["id"] == "nemotron-3-super-nim" and rec["fallbacks"] == ["qwen3.5-4b"]


def test_local_only_mode_still_wins(home, monkeypatch):
    from bau import localonly
    _online(monkeypatch, True)
    localonly.set_mode(home, "local-only", "human:owner", None)
    _, rec = pick_model(home)
    assert rec["id"] == "qwen3.5-4b"


# ------------------------------------------------------------------ the setup pop-up
def test_unapproved_keys_pop_up_a_step_to_use_them(home, monkeypatch):
    from bau import setup_steps as S
    reg = CapabilityRegistry(home / "registry" / "capabilities.yaml")
    reg.data["model"]["nemotron-3-super-nim"]["status"] = "PROPOSED"
    reg.save()
    facts = {"nvidia": False, "driver": False, "pictures": False, "search": True,
             "update": "auto", "autopilot": True}
    assert [s.id for s in S.waiting(home, probe=facts.__getitem__)] == ["api_keys"]
    opened = []
    S.run("api_keys", home, probe=facts.__getitem__,
          terminal=lambda t, c: opened.append(c) or True)
    assert "bau set-status model nemotron-3-super-nim APPROVED" in opened[0]
    assert "trial" in S.BY_ID["api_keys"].why.lower()      # NVIDIA's terms said plainly
