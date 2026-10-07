"""Free hosted GLM-4.7-Flash (Z.ai) and the Codespaces test drive."""

import json

import pytest
import yaml

from bau.models.providers import OpenAICompatProvider, build
from bau.registry import CapabilityRegistry, validate
from bau.runtime import seed_registry, shipped_data


def defaults():
    return yaml.safe_load((shipped_data() / "registry_defaults.yaml").read_text())


class FakeAPI:
    def __init__(self):
        self.reqs = []

    def __call__(self, req, timeout=0):
        self.reqs.append(req)
        out = json.dumps({"model": "glm-4.7-flash", "choices": [{"message": {
            "role": "assistant", "content": "Hello! Teal."}}],
            "usage": {"prompt_tokens": 9, "completion_tokens": 3}}).encode()

        class R:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return out
        return R()


def test_zai_record_is_free_cloud_and_needs_owner_approval():
    d = defaults()
    m, p = d["model"]["glm-4.7-flash-zai"], d["provider"]["zai"]
    assert m["status"] == "REGISTERED" and m["deployment"] == "cloud" and m["provider"] == "zai"
    assert m["cost_in_per_mtok"] == 0 and m["cost_out_per_mtok"] == 0
    assert m["endpoint"].startswith("https://") and m["api_key_env"] == "ZAI_API_KEY"
    assert "key" not in json.dumps(m).replace("api_key_env", "")    # never a key in the repo
    assert validate("model", m) == [] and validate("provider", p) == []
    assert p["jurisdiction"] == "SG" and "not stated" in p["training_on_customer_data"]


def test_hosted_provider_sends_key_header_path_and_thinking_off(monkeypatch):
    monkeypatch.setenv("ZAI_API_KEY", "test-key-123")
    prov = build(defaults()["model"]["glm-4.7-flash-zai"])
    assert isinstance(prov, OpenAICompatProvider)
    api = FakeAPI()
    prov._open = api
    r = prov.complete("Be brief.", [{"role": "user", "content": "Colour?"}])
    req = api.reqs[0]
    assert req.full_url == "https://api.z.ai/api/paas/v4/chat/completions"
    assert req.get_header("Authorization") == "Bearer test-key-123"
    body = json.loads(req.data)
    assert body["model"] == "glm-4.7-flash" and body["thinking"] == {"type": "disabled"}
    assert r.text == "Hello! Teal." and r.tokens_out == 3


def test_hosted_model_without_key_is_unavailable_not_faked(monkeypatch):
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    with pytest.raises(PermissionError, match="ZAI_API_KEY"):
        build(defaults()["model"]["glm-4.7-flash-zai"])


def test_jarvis_uses_zai_once_approved_and_keyed(tmp_path, monkeypatch):
    from bau.assistant import build_assistant
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    seed_registry(tmp_path)
    path = tmp_path / "registry" / "capabilities.yaml"
    data = yaml.safe_load(path.read_text())
    data["model"]["glm-4.7-flash-zai"]["status"] = "APPROVED"
    path.write_text(yaml.safe_dump(data))
    assert build_assistant(tmp_path).provider is None             # no key: basic mode
    monkeypatch.setenv("ZAI_API_KEY", "k")
    a = build_assistant(tmp_path)
    assert a.model["id"] == "glm-4.7-flash-zai" and isinstance(a.provider, OpenAICompatProvider)


def test_seeding_adds_new_records_and_keeps_owner_approvals(tmp_path):
    seed_registry(tmp_path)
    reg = CapabilityRegistry(tmp_path / "registry" / "capabilities.yaml")
    reg.data["model"]["claude-opus-5-5"]["status"] = "APPROVED"
    del reg.data["model"]["glm-4.7-flash-zai"]                    # an install from before
    reg.path.write_text(yaml.safe_dump(reg.data))
    seed_registry(tmp_path)
    again = CapabilityRegistry(tmp_path / "registry" / "capabilities.yaml")
    assert "glm-4.7-flash-zai" in again.data["model"]
    assert again.data["model"]["claude-opus-5-5"]["status"] == "APPROVED"


def test_codespaces_ports_stay_private_and_named():
    import re
    from pathlib import Path
    raw = (Path(__file__).resolve().parents[1] / ".devcontainer" / "devcontainer.json").read_text()
    cfg = json.loads(re.sub(r"^\s*//.*$", "", raw, flags=re.M))
    assert cfg["forwardPorts"] == [8765, 8766]
    assert all(a.get("visibility", "private") == "private"
               for a in cfg["portsAttributes"].values())
    hosts = cfg["remoteEnv"]["BAU_UI_ALLOWED_HOSTS"].split(",")
    assert [h.split(".")[0].rsplit("-", 1)[1] for h in hosts] == ["8765", "8766"]


def test_jarvis_prints_the_private_codespace_link(monkeypatch, capsys, tmp_path):
    from bau import cli_ext
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    monkeypatch.setenv("CODESPACE_NAME", "fuzzy-train")
    monkeypatch.setenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")

    class Srv:
        def serve_forever(self):
            raise KeyboardInterrupt
    monkeypatch.setattr("bau.ui.jarvis_server.serve", lambda jv, v, port: (Srv(), "KEY"))
    monkeypatch.setattr(cli_ext, "_human", lambda: "human:owner")   # the owner's terminal

    class A:
        jv_cmd, text, port, no_browser = None, False, 8766, True
    assert cli_ext.cmd_jarvis(A()) == 0
    assert "https://fuzzy-train-8766.app.github.dev/?k=KEY" in capsys.readouterr().err
