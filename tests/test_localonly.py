"""Local only: when the owner turns it on, no model call leaves this computer (owner's
decision 2026-10-26: cloud models keep the data, so Claude, OpenAI, Z.ai and NVIDIA's
hosted models are off). Every model is built in providers.build(), so the check is there."""

import pytest

from bau import localonly as privacy
from bau.audit import AuditLog
from bau.models.providers import build

CLAUDE = {"model_id": "claude-opus-5-5", "adapter": "anthropic", "deployment": "cloud"}
ZAI = {"model_id": "glm", "adapter": "openai_compat", "deployment": "cloud",
       "endpoint": "https://api.z.ai/api/paas/v4", "api_key_env": "ZAI_API_KEY"}
QWEN = {"model_id": "qwen3.5-9b", "adapter": "local_http", "deployment": "local",
        "endpoint": "http://127.0.0.1:8080"}


def _on(home):
    privacy.set_mode(home, "local-only", "human:owner", AuditLog(home / "a.jsonl"))


def test_not_chosen_until_the_owner_chooses(isolated_home, monkeypatch):
    monkeypatch.setenv("ZAI_API_KEY", "x")
    assert privacy.mode(isolated_home) is None
    build(ZAI)                                         # unchanged behaviour until then


def test_local_only_refuses_every_cloud_model(isolated_home, monkeypatch):
    monkeypatch.setenv("ZAI_API_KEY", "x")
    _on(isolated_home)
    for rec in (CLAUDE, ZAI):
        with pytest.raises(PermissionError, match="local only"):
            build(rec)
    build(QWEN)                                        # the model on this computer still works


def test_a_local_label_on_a_far_away_server_is_refused(isolated_home):
    # The record says "local" but points at another computer: the address decides.
    _on(isolated_home)
    with pytest.raises(PermissionError, match="local only"):
        build({**QWEN, "endpoint": "http://203.0.113.9:8080"})
    for ok in ("http://localhost:8080", "http://[::1]:8080"):
        build({**QWEN, "endpoint": ok})


def test_the_container_model_server_counts_as_local(isolated_home, monkeypatch):
    _on(isolated_home)
    monkeypatch.setenv("BAU_LLM_ENDPOINT", "http://llm:8080")
    build(QWEN)
    with pytest.raises(PermissionError):
        build(CLAUDE)


def test_only_a_person_sets_it(isolated_home):
    with pytest.raises(PermissionError):
        privacy.set_mode(isolated_home, "cloud", "jarvis", None)
    with pytest.raises(ValueError):
        privacy.set_mode(isolated_home, "sometimes", "human:owner", None)


def test_jarvis_skips_cloud_models_when_local_only(isolated_home, monkeypatch):
    from bau.assistant import pick_model
    from bau.registry import CapabilityRegistry
    from bau.runtime import seed_registry
    seed_registry(isolated_home)
    reg = CapabilityRegistry(isolated_home / "registry" / "capabilities.yaml")
    monkeypatch.setenv("ZAI_API_KEY", "x")
    reg.data["model"]["glm-4.7-flash-zai"]["status"] = "APPROVED"   # comes first in the order
    reg.data["model"]["qwen3.5-4b"]["status"] = "APPROVED"
    reg.save()
    _on(isolated_home)
    _, rec = pick_model(isolated_home)
    assert rec["model_id"] == "qwen3.5-4b"


def test_the_specialist_check_says_so_instead_of_crashing(isolated_home):
    from bau import agentfolders as AF
    assert "local only" in AF.not_checked(PermissionError("local only is on"))


def test_team_refuses_a_cloud_specialist_when_local_only(isolated_home):
    from bau import team
    from bau.runtime import seed_registry
    seed_registry(isolated_home)
    _on(isolated_home)
    with pytest.raises(ValueError, match="local only"):
        team.set_team(isolated_home, "human:owner", None, specialist="claude-opus-5-5")


def test_the_command_needs_a_person_and_shows_the_choice(tmp_path):
    import subprocess
    import sys
    env = {"BAU_HOME": str(tmp_path), "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    run = [sys.executable, "-m", "bau.cli", "privacy"]
    r = subprocess.run(run, capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0 and "not chosen yet" in r.stdout
    r = subprocess.run([*run, "cloud"], capture_output=True, text=True, env=env, timeout=60,
                       stdin=subprocess.DEVNULL)
    assert r.returncode != 0 and "human" in r.stderr
    assert privacy.mode(tmp_path) is None
