"""NVIDIA Nemotron 3 Super as a free backup model: the record, the fallback chain, and the
personal-data rule from NVIDIA's API Trial terms."""

import io
import json
import urllib.error
import zipfile

import pytest
import yaml

from bau.assistant import Assistant, build_assistant
from bau.audit import AuditLog
from bau.chats import ChatLibrary
from bau.models.providers import (
    FallbackProvider,
    OpenAICompatProvider,
    ProviderError,
    ScriptedProvider,
    build,
)
from bau.registry import validate
from bau.runtime import seed_registry, shipped_data


def defaults():
    return yaml.safe_load((shipped_data() / "registry_defaults.yaml").read_text())


def approve(home, *mids):
    seed_registry(home)
    path = home / "registry" / "capabilities.yaml"
    data = yaml.safe_load(path.read_text())
    for mid in mids:
        data["model"][mid]["status"] = "APPROVED"
    path.write_text(yaml.safe_dump(data))


def test_record_is_a_trial_only_cloud_model_that_waits_for_the_owner():
    d = defaults()
    m, p = d["model"]["nemotron-3-super-nim"], d["provider"]["nvidia"]
    assert validate("model", m) == [] and validate("provider", p) == []
    assert m["status"] == "REGISTERED" and p["status"] == "REGISTERED"   # owner approves
    assert m["deployment"] == "cloud" and m["commercial_use"] is False
    assert m["endpoint"] == "https://integrate.api.nvidia.com/v1"
    assert m["api_key_env"] == "NVIDIA_API_KEY" and m["cost_out_per_mtok"] == 0
    assert p["personal_data_allowed"] is False and "trial" in p["commercial_rights"]
    assert "key" not in json.dumps(m).replace("api_key_env", "")


def test_it_calls_nvidias_endpoint_with_the_key(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nv-test")
    prov = build(defaults()["model"]["nemotron-3-super-nim"])
    sent = []

    class R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"model": "nvidia/nemotron-3-super-120b-a12b",
                               "choices": [{"message": {"content": "Hi."}}]}).encode()

    prov._open = lambda req, timeout=0: sent.append(req) or R()
    assert isinstance(prov, OpenAICompatProvider) and prov.complete("s", []).text == "Hi."
    assert sent[0].full_url == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert sent[0].get_header("Authorization") == "Bearer nv-test"
    assert json.loads(sent[0].data)["model"] == "nvidia/nemotron-3-super-120b-a12b"


def busy():
    return ProviderError("https://api.z.ai/api/paas/v4 is busy (HTTP 429): overloaded")


class Flaky(ScriptedProvider):
    def complete(self, *a, **kw):
        if self.script and self.script[0] == "BUSY":
            self.script.pop(0)
            raise busy()
        if self.script and self.script[0] == "HANG":
            self.script.pop(0)
            raise TimeoutError("The read operation timed out")
        return super().complete(*a, **kw)


def test_backup_answers_when_the_first_is_busy_and_the_first_rests():
    zai, nim = Flaky(script=["BUSY", "Z back."]), Flaky(script=["N one.", "N two."])
    fb = FallbackProvider([zai, nim])
    t = [1000.0]
    fb.clock = lambda: t[0]
    assert fb.complete("s", [{"role": "user", "content": "hi"}]).text == "N one."
    assert fb.complete("s", [{"role": "user", "content": "hi"}]).text == "N two."   # resting
    assert zai.script == ["Z back."]                    # not asked again while resting
    t[0] += FallbackProvider.REST + 1
    assert fb.complete("s", [{"role": "user", "content": "hi"}]).text == "Z back."


def test_when_every_model_fails_the_owner_hears_why(tmp_path):
    fb = FallbackProvider([Flaky(script=["BUSY"]), Flaky(script=["HANG"])])
    with pytest.raises(ProviderError, match="every approved model failed: .*overloaded.*timed"):
        fb.complete("s", [])
    a = Assistant(tmp_path, FallbackProvider([Flaky(script=["BUSY"]), Flaky(script=["BUSY"])]),
                  {}, "human:owner", AuditLog(tmp_path / "audit" / "chain.jsonl", key=b""))
    r = a.ask("hello")
    assert "couldn't reach my model" in r.text and "every approved model failed" in r.text
    assert a.messages == []


def test_jarvis_chains_approved_hosted_models_in_order(tmp_path, monkeypatch):
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    monkeypatch.setenv("ZAI_API_KEY", "z")
    monkeypatch.setenv("NVIDIA_API_KEY", "n")
    approve(tmp_path, "nemotron-3-super-nim")
    a = build_assistant(tmp_path)                       # only NVIDIA: no chain
    assert a.model["id"] == "nemotron-3-super-nim" and isinstance(a.provider,
                                                                   OpenAICompatProvider)
    approve(tmp_path, "glm-4.7-flash-zai", "nemotron-3-super-nim")
    a = build_assistant(tmp_path)
    assert isinstance(a.provider, FallbackProvider)
    assert a.model["id"] == "glm-4.7-flash-zai"
    assert a.model["fallbacks"] == ["nemotron-3-super-nim"]
    assert [p.model for p in a.provider.providers] == ["glm-4.7-flash",
                                                       "nvidia/nemotron-3-super-120b-a12b"]
    monkeypatch.delenv("NVIDIA_API_KEY")                # no key: no backup, nothing faked
    assert isinstance(build_assistant(tmp_path).provider, OpenAICompatProvider)


def test_old_chats_never_go_to_a_provider_that_forbids_personal_data(tmp_path, monkeypatch):
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    monkeypatch.setenv("ZAI_API_KEY", "z")
    monkeypatch.setenv("NVIDIA_API_KEY", "n")
    zipped = tmp_path / "c.zip"
    with zipfile.ZipFile(zipped, "w") as z:
        z.writestr("conversations.json", json.dumps([{
            "uuid": "c1", "name": "Ducks", "created_at": "2026-05-01T00:00:00Z",
            "chat_messages": [{"sender": "human", "text": "ducks", "created_at": ""}]}]))
    lib = ChatLibrary(tmp_path)
    lib.import_file(zipped)
    lib.set_sharing("cloud")                            # even the owner's 'cloud' choice
    approve(tmp_path, "glm-4.7-flash-zai")
    out, err = build_assistant(tmp_path)._run_tool("chat_search", {"query": "ducks"})
    assert not err and out[0]["conversation"] == "claude/c1"            # Z.ai alone: allowed
    approve(tmp_path, "glm-4.7-flash-zai", "nemotron-3-super-nim")      # NVIDIA as backup
    out, err = build_assistant(tmp_path)._run_tool("chat_search", {"query": "ducks"})
    assert err and "nemotron-3-super-nim's terms don't allow personal data" in out["error"]


def test_http_errors_from_the_backup_are_handled_like_any_hosted_model(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "n")
    nim = build(defaults()["model"]["nemotron-3-super-nim"])

    def gone(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 410, "Gone", {}, io.BytesIO(b"{}"))
    nim._open = gone
    fb = FallbackProvider([Flaky(script=["BUSY"]), nim])
    with pytest.raises(ProviderError, match="HTTP 410"):
        fb.complete("s", [])
