"""Colibri on the laptop (installer/bau-colibri-setup.sh, docs/COLIBRI.md): the model record,
its local server, and the installer's pins. No network: Colibri's answers are faked."""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import yaml

from bau import localonly as privacy
from bau.audit import AuditLog
from bau.models.providers import LocalHTTPProvider, ToolSpec, build
from bau.runtime import seed_registry

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "installer" / "bau-colibri-setup.sh").read_text()
SUMS = ROOT / "installer" / "colibri" / "qwen3-coder-30b.sha256"
OIDS = ROOT / "installer" / "colibri" / "qwen3-coder-30b.gitoid"
ID = "qwen3-coder-30b-colibri"


def record(home: Path) -> dict:
    seed_registry(home)
    reg = yaml.safe_load((home / "registry" / "capabilities.yaml").read_text())
    return reg["model"][ID]


def test_the_laptop_model_is_registered_local_and_never_approved(tmp_path):
    m = record(tmp_path)
    assert m["status"] == "REGISTERED"            # only the owner approves, after the bench
    assert m["endpoint"] == "http://127.0.0.1:8000" and m["deployment"] == "local"
    assert m["tools"] is True and m["license"] == "Apache-2.0"
    assert m["api_model"] == "qwen3-coder-30b-a3b-colibri"   # the gateway's own model id


def test_it_runs_with_local_only_on(tmp_path):
    m = record(tmp_path)
    privacy.set_mode(tmp_path, "local-only", "human:owner", AuditLog(tmp_path / "a.jsonl"))
    privacy.check(m, tmp_path)                    # no PermissionError: it stays on 127.0.0.1
    assert privacy.is_local(m)


def test_jarvis_reads_a_colibri_tool_call(tmp_path):
    m = record(tmp_path)
    sent = []

    class Reply(io.BytesIO):
        headers: dict = {}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(req, timeout=0):
        sent.append((req.full_url, json.loads(req.data)))
        return Reply(json.dumps({"model": "qwen3-coder-30b-a3b-colibri", "choices": [{
            "message": {"role": "assistant", "content": "", "tool_calls": [{
                "id": "c1", "type": "function", "function": {
                    "name": "money", "arguments": "{\"days\": 7}"}}]}}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 12}}).encode())

    p = build(m)
    assert isinstance(p, LocalHTTPProvider) and p.base_url == "http://127.0.0.1:8000"
    p._open = opener
    r = p.complete("You are Jarvis.", [{"role": "user", "content": "money this week?"}],
                   tools=[ToolSpec("money", "the books", {"type": "object", "properties": {
                       "days": {"type": "integer"}}})])
    assert sent[0][0] == "http://127.0.0.1:8000/v1/chat/completions"
    assert sent[0][1]["model"] == "qwen3-coder-30b-a3b-colibri"
    assert r.tool_calls[0].name == "money" and r.tool_calls[0].input == {"days": 7}


def test_the_installer_pins_every_file():
    sums = [ln.split() for ln in SUMS.read_text().splitlines()]
    oids = [ln.split() for ln in OIDS.read_text().splitlines()]
    names = [n for _, n in sums]
    assert names == [f"model-{i:05d}.safetensors" for i in range(48)] + [
        "model-globals.safetensors"]
    assert all(re.fullmatch(r"[0-9a-f]{64}", s) for s, _ in sums)
    assert len({s for s, _ in sums}) == len(sums)              # no line copied twice
    assert {n for _, n in oids} >= {"config.json", "tokenizer.json", "qwen36_meta.json",
                                    "chat_template.jinja", "tokenizer_config.json"}
    assert all(re.fullmatch(r"[0-9a-f]{40}", o) for o, _ in oids)
    for name in ("COLIBRI_COMMIT", "MODEL_COMMIT"):
        assert re.search(rf'^{name}="[0-9a-f]{{40}}"', SCRIPT, re.M), name
    assert "resolve/${MODEL_COMMIT}" in SCRIPT and "/resolve/main" not in SCRIPT
    assert 'rev-parse HEAD) == "${COLIBRI_COMMIT}"' in SCRIPT
    assert SCRIPT.count("sha256sum -c") >= 2 and "git hash-object" in SCRIPT


def test_the_installer_keeps_it_on_this_computer():
    assert "--host 127.0.0.1 --port 8000" in SCRIPT
    assert "0.0.0.0" not in SCRIPT and "--api-key" not in SCRIPT
    assert "IPAddressDeny=any" in SCRIPT and "IPAddressAllow=localhost" in SCRIPT
    assert "NoNewPrivileges=yes" in SCRIPT and "User=bau" in SCRIPT
    assert "/run/live/medium" in SCRIPT                # refuses the live stick
    assert "7300000" in SCRIPT                         # refuses under 8 GB
