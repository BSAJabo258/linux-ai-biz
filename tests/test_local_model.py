import json

import pytest
import yaml

from bau.assistant import Assistant, build_assistant
from bau.audit import AuditLog
from bau.models.bench import benchmark
from bau.models.providers import LocalHTTPProvider, ScriptedProvider, build
from bau.registry import validate


class FakeServer:
    """llama.cpp llama-server's OpenAI-compatible chat endpoint."""

    def __init__(self, think_only=False):
        self.bodies, self.think_only = [], think_only

    def __call__(self, req, timeout=0):
        body = json.loads(req.data)
        self.bodies.append(body)
        if body.get("tools"):
            msg = {"role": "assistant", "content": "", "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "get_time", "arguments": "{}"}}]}
        else:
            msg = {"role": "assistant",
                   "content": "<think>long thoughts</think>" + ("" if self.think_only
                                                                else "Hello! Blue.")}
        out = json.dumps({"model": "glm-4.7-flash", "choices": [{"message": msg}],
                          "usage": {"prompt_tokens": 20, "completion_tokens": 40}}).encode()

        class R:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return out
        return R()


def glm_record():
    from bau.runtime import shipped_data
    return yaml.safe_load((shipped_data() / "registry_defaults.yaml").read_text()
                          )["model"]["glm-4.7-flash"]


def test_glm_record_is_free_local_and_needs_a_real_benchmark():
    rec = glm_record()
    assert rec["license"] == "MIT" and rec["commercial_use"] and rec["deployment"] == "local"
    assert rec["trust_level"] == "QUANTIZED" and rec["status"] == "REGISTERED"
    assert any("benchmark" in e for e in validate("model", {**rec, "status": "APPROVED"}))
    bad = {**rec, "status": "APPROVED", "benchmark": {"reply_ok": False}}
    assert any("no answer" in e for e in validate("model", bad))
    assert validate("model", {**rec, "status": "APPROVED", "benchmark": {"reply_ok": True}}) == []


def test_benchmark_measures_reply_speed_and_tool_use():
    fake = FakeServer()
    p = LocalHTTPProvider("http://llm:8080", "glm-4.7-flash", opener=fake,
                          template_kwargs={"enable_thinking": False})
    res = benchmark(glm_record(), p)
    assert res["reply_ok"] and res["tool_calls"] and res["endpoint"] == "http://llm:8080"
    assert res["tokens_per_sec"] and res["served_model"] == "glm-4.7-flash"
    assert fake.bodies[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert not benchmark(glm_record(), LocalHTTPProvider(opener=FakeServer(think_only=True))
                         )["reply_ok"]      # thinking with no answer is not a working model


def test_thinking_is_never_spoken_and_container_endpoint_override(monkeypatch):
    r = LocalHTTPProvider(opener=FakeServer()).complete("s", [{"role": "user", "content": "hi"}])
    assert r.text == "Hello! Blue."
    monkeypatch.setenv("BAU_LLM_ENDPOINT", "http://llm:8080")
    assert build(glm_record()).base_url == "http://llm:8080"
    assert build(glm_record()).template_kwargs == {"enable_thinking": False}
    cloud = {"model_id": "x", "adapter": "local_http", "deployment": "remote",
             "endpoint": "http://k3:8080"}
    assert build(cloud).base_url == "http://k3:8080"          # only on-machine models move


def test_bind_address_is_local_unless_in_the_container(monkeypatch):
    from bau.ui.server import bind_address
    monkeypatch.delenv("BAU_IN_CONTAINER", raising=False)
    assert bind_address() == "127.0.0.1"
    monkeypatch.setenv("BAU_IN_CONTAINER", "1")
    assert bind_address() == "0.0.0.0"


def test_jarvis_never_reads_data_blocks_aloud(tmp_path):
    echo = ('<untrusted_data source="bau_facts">{"secret": 1}</untrusted_data> '
            "All quiet tonight.")
    a = Assistant(tmp_path, ScriptedProvider(script=[echo, "<untrusted_data x>{...}"]), {},
                  "human:owner", AuditLog(tmp_path / "audit" / "chain.jsonl", key=b""))
    assert a.briefing().text == "All quiet tonight."
    assert "boss" in a.briefing().text           # only an echo: fall back to the facts


def test_jarvis_falls_back_to_glm_when_claude_is_not_approved(tmp_path, monkeypatch):
    from bau.runtime import seed_registry
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    seed_registry(tmp_path)
    path = tmp_path / "registry" / "capabilities.yaml"
    data = yaml.safe_load(path.read_text())
    data["model"]["glm-4.7-flash"].update(status="APPROVED", benchmark={"reply_ok": True})
    path.write_text(yaml.safe_dump(data))
    a = build_assistant(tmp_path, owner="human:x")
    assert a.model["id"] == "glm-4.7-flash" and isinstance(a.provider, LocalHTTPProvider)


@pytest.mark.parametrize("name", ["Dockerfile", "docker-compose.yml"])
def test_container_files_keep_ports_local(name):
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / name).read_text()
    if name == "docker-compose.yml":
        ports = [ln for ln in text.splitlines() if "ports:" in ln]
        assert ports and all("127.0.0.1:" in ln for ln in ports)
    else:
        assert "USER owner" in text and "BAU_IN_CONTAINER=1" in text


def test_scripts_keep_lf_line_endings_on_windows_checkouts():
    # Seen 2026-10-08: an image built from the owner's Windows checkout restarted 948
    # times with "exec bau-entrypoint failed: No such file or directory" ("#!/bin/sh\r").
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    attrs = (root / ".gitattributes").read_text().splitlines()
    assert "* text=auto eol=lf" in attrs and "*.ps1 text eol=crlf" in attrs
    docker = (root / "Dockerfile").read_text()
    installed = re.findall(r"^COPY --chmod=0755 \S+ (/usr/local/bin/\S+)$", docker, re.M)
    strip = re.search(r"^RUN sed -i 's/\\r\$//' (.+)$", docker, re.M)
    assert installed and strip and set(installed) <= set(strip.group(1).split())
    assert docker.index(strip.group(0)) < docker.index("USER owner")    # still root
