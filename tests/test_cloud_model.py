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
    from bau.assistant import CONVERSATION_WAITS
    assert a.provider.waits == CONVERSATION_WAITS and sum(CONVERSATION_WAITS) <= 30
    assert build(defaults()["model"]["glm-4.7-flash-zai"]).waits == (5, 10, 20, 40)  # bench


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


def test_codespace_comes_with_ssh_and_claude_code_from_official_features():
    # `gh codespace ssh` needs an SSH server in the image (it had none on 2026-10-10), and
    # the owner wanted Claude Code in the codespace terminal. Official features only.
    import re
    from pathlib import Path
    raw = (Path(__file__).resolve().parents[1] / ".devcontainer" / "devcontainer.json").read_text()
    feats = json.loads(re.sub(r"^\s*//.*$", "", raw, flags=re.M))["features"]
    assert set(feats) == {"ghcr.io/devcontainers/features/sshd:1",
                          "ghcr.io/devcontainers/features/node:1",
                          "ghcr.io/anthropics/devcontainer-features/claude-code:1.0"}
    # Without Node the Claude Code feature fails, the whole build fails, and Codespaces
    # falls back to a bare recovery container (no SSH, no BAU): Node must come first.
    order = list(feats)
    assert order.index("ghcr.io/devcontainers/features/node:1") < order.index(
        "ghcr.io/anthropics/devcontainer-features/claude-code:1.0")


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


def _busy(code, body):
    import io
    import urllib.error
    return urllib.error.HTTPError("https://api.z.ai/x", code, "Too Many Requests", {},
                                  io.BytesIO(body))


def test_busy_free_service_is_retried_then_answers(monkeypatch):
    monkeypatch.setenv("ZAI_API_KEY", "test-key-123")
    prov = build(defaults()["model"]["glm-4.7-flash-zai"])
    ok, waited = FakeAPI(), []
    replies = [_busy(429, b'{"error":{"code":"1305","message":"overloaded"}}')] * 2

    def flaky(req, timeout=0):
        if replies:
            raise replies.pop()
        return ok(req, timeout)
    prov._open, prov.sleep = flaky, waited.append
    assert prov.complete("Be brief.", [{"role": "user", "content": "Hi"}]).text == "Hello! Teal."
    assert waited == [5, 10]


def test_busy_too_long_or_refused_shows_the_service_message_not_the_key(monkeypatch):
    from bau.models.providers import ProviderError
    monkeypatch.setenv("ZAI_API_KEY", "test-key-123")
    prov = build(defaults()["model"]["glm-4.7-flash-zai"])
    waited = []

    def busy(req, timeout=0):
        raise _busy(429, b'{"error":{"code":"1305","message":"The service may be '
                         b'temporarily overloaded"}}')
    prov._open, prov.sleep = busy, waited.append
    with pytest.raises(ProviderError, match="busy .*temporarily overloaded.*try again") as e:
        prov.complete("s", [{"role": "user", "content": "Hi"}])
    assert len(waited) == 4 and "test-key-123" not in str(e.value)

    def refused(req, timeout=0):
        raise _busy(401, b'{"error":{"code":"1000","message":"Authentication failed"}}')
    prov._open, waited[:] = refused, []
    with pytest.raises(ProviderError, match="HTTP 401.*Authentication failed"):
        prov.complete("s", [{"role": "user", "content": "Hi"}])
    assert waited == []                                     # a wrong key is not retried


def test_one_off_server_error_is_retried(monkeypatch):
    monkeypatch.setenv("ZAI_API_KEY", "test-key-123")
    prov = build(defaults()["model"]["glm-4.7-flash-zai"])
    ok, waited = FakeAPI(), []
    replies = [_busy(500, b'{"error":{"code":"500","message":"Operation failed"}}')]

    def flaky(req, timeout=0):
        if replies:
            raise replies.pop()
        return ok(req, timeout)
    prov._open, prov.sleep = flaky, waited.append
    assert prov.complete("s", [{"role": "user", "content": "Hi"}]).text == "Hello! Teal."
    assert waited == [5]


@pytest.mark.parametrize("module", ["jarvis_server", "server"])
def test_a_browser_that_hangs_up_is_not_an_error(monkeypatch, tmp_path, module):
    import importlib
    from http.server import BaseHTTPRequestHandler
    mod = importlib.import_module(f"bau.ui.{module}")
    if module == "jarvis_server":
        from bau.assistant import Assistant, Voice
        h = mod.make_handler(Assistant(tmp_path), Voice(), "k")
    else:
        h = mod.make_handler(tmp_path)
    for err in (BrokenPipeError, ConnectionResetError):
        def gone(self, err=err):
            raise err(32, "Broken pipe")
        monkeypatch.setattr(BaseHTTPRequestHandler, "handle", gone)
        h.handle(h.__new__(h))                               # no traceback, no crash


def test_jarvis_page_reads_every_reply_through_the_safe_helper():
    from pathlib import Path
    page = (Path(__file__).resolve().parents[1] / "src" / "bau" / "ui" / "jarvis.html"
            ).read_text(encoding="utf-8")
    assert "async function apiJson" in page
    assert ".json()" not in page                 # an empty or HTML reply never hits JSON.parse raw


def test_jarvis_answers_politely_when_the_model_fails_and_keeps_history_clean(tmp_path):
    from bau.assistant import Assistant
    from bau.audit import AuditLog
    from bau.models.providers import ProviderError, ScriptedProvider

    class Failing(ScriptedProvider):
        def complete(self, *a, **kw):
            if self.script and self.script[0] == "FAIL":
                self.script.pop(0)
                raise ProviderError("https://api.z.ai/api/paas/v4 refused the request "
                                    "(HTTP 500): Operation failed")
            return super().complete(*a, **kw)

    prov = Failing(script=[{"tool": "money", "input": {}}, "FAIL", "Fine now."])
    a = Assistant(tmp_path, prov, {}, "human:owner",
                  AuditLog(tmp_path / "audit" / "chain.jsonl", key=b""))
    r = a.ask("How is money?")                      # fails after a tool call, mid-turn
    assert "couldn't reach my model" in r.text and "Operation failed" in r.text
    assert a.messages == []                         # no half-finished exchange left behind
    assert a.ask("How is money?").text == "Fine now."
    assert [m["role"] for m in a.messages] == ["user", "assistant"]
