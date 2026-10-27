"""Speed settings for the model server (docs/GPU.md section 4): a model's own settings
(MTP draft head) pass through only from an allowed list, and the owner's tune file."""

import argparse
from pathlib import Path

import pytest
import yaml

from bau import pack
from bau.home import shipped_data

UNIT = (Path(__file__).resolve().parents[1] / "image/live-build/config/includes.chroot"
        / "etc/systemd/system/bau-llm.service")


def _reg():
    return yaml.safe_load((shipped_data() / "registry_defaults.yaml").read_text())["model"]


def _start(tmp_path, rec):
    ran = []
    ok = pack._start("m", rec, tmp_path / "models", tmp_path / "etc",
                     lambda c: ran.append(c) or "", lambda *a: None)
    return ok, ran


def test_an_mtp_model_starts_with_its_draft_head_on(tmp_path):
    ok, ran = _start(tmp_path, _reg()["qwen3.5-9b-mtp"])
    env = (tmp_path / "etc" / "llm.env").read_text().splitlines()
    assert ok and ran == [["systemctl", "restart", "bau-llm.service"]]
    assert env[0].endswith("models/Qwen3.5-9B-MTP-Q4_K_M.gguf")
    assert env[1:] == ["BAU_LLM_ALIAS=qwen3.5-9b-mtp", "LLAMA_ARG_SPEC_TYPE=draft-mtp",
                       "LLAMA_ARG_SPEC_DRAFT_N_MAX=3", "LLAMA_ARG_N_PARALLEL=1"]


def test_a_plain_model_gets_only_its_file_and_name(tmp_path):
    _start(tmp_path, _reg()["qwen3.5-9b"])
    assert len((tmp_path / "etc" / "llm.env").read_text().splitlines()) == 2


@pytest.mark.parametrize("extra", [
    {"LLAMA_ARG_HOST": "0.0.0.0"},                          # not on the list
    {"LLAMA_ARG_SPEC_TYPE": "draft-mtp\nLLAMA_ARG_HOST=0.0.0.0"},   # a second line
    {"LLAMA_ARG_SPEC_DRAFT_N_MAX": "/etc/shadow"},
])
def test_a_record_cannot_open_the_server_up(tmp_path, extra):
    rec = dict(_reg()["qwen3.5-9b"], server_env=extra)
    with pytest.raises(pack.PackError, match="not allowed"):
        _start(tmp_path, rec)
    assert not (tmp_path / "etc" / "llm.env").exists()


def test_tune_writes_the_owners_settings_and_restarts(tmp_path):
    ran = []
    run = lambda c: ran.append(c) or ""                   # noqa: E731
    etc = tmp_path / "etc"
    assert pack.tune(etc, run, draft="4") == {"LLAMA_ARG_SPEC_DRAFT_N_MAX": "4"}
    pack.tune(etc, run, kv="q8_0")                         # keeps the draft length
    assert (etc / "llm-tune.env").read_text().splitlines() == [
        "LLAMA_ARG_CACHE_TYPE_K=q8_0", "LLAMA_ARG_CACHE_TYPE_V=q8_0",
        "LLAMA_ARG_SPEC_DRAFT_N_MAX=4"]
    now = pack.tune(etc, run, draft="off")
    assert now["LLAMA_ARG_SPEC_TYPE"] == "none" and "LLAMA_ARG_SPEC_DRAFT_N_MAX" not in now
    pack.tune(etc, run, reset=True)                        # back to llama.cpp's defaults
    assert not (etc / "llm-tune.env").exists()
    assert ran == [["systemctl", "restart", "bau-llm.service"]] * 4


@pytest.mark.parametrize("kw", [{"draft": "0"}, {"draft": "17"}, {"draft": "3; rm"},
                                {"kv": "q8_0\nLLAMA_ARG_HOST=0.0.0.0"}, {"kv": "f32"}])
def test_tune_refuses_anything_else(tmp_path, kw):
    with pytest.raises(ValueError):
        pack.tune(tmp_path, lambda c: "", **kw)
    assert not (tmp_path / "llm-tune.env").exists()


def test_the_service_reads_the_tune_file_last():
    text = UNIT.read_text()
    assert "EnvironmentFile=-/etc/bau/llm-tune.env" in text
    assert text.index("llm-engine.env") < text.index("llm-tune.env") < text.index("ExecStart=")


def test_the_mtp_files_are_pinned_and_not_approved():
    reg = _reg()
    for mid, size in (("qwen3.5-9b-mtp", 5_868_826_976), ("qwen3.5-4b-mtp", 2_834_975_040)):
        rec = reg[mid]
        assert rec["status"] == "REGISTERED" and rec["license"] == "Apache-2.0"
        assert rec["download"]["size"] == size and len(rec["download"]["sha256"]) == 64
        assert set(rec["server_env"]) <= pack.SERVER_ENV
        assert rec["chat_template_kwargs"] == {"enable_thinking": False}


def test_tune_needs_sudo_and_a_human(monkeypatch):
    from bau import cli_ext
    a = argparse.Namespace(models_cmd="tune", draft="3", kv=None, reset=False)
    monkeypatch.setattr("os.geteuid", lambda: 1000)
    with pytest.raises(SystemExit, match="sudo"):
        cli_ext.cmd_models(a)
    monkeypatch.setattr("os.geteuid", lambda: 0)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(PermissionError):
        cli_ext.cmd_models(a)
