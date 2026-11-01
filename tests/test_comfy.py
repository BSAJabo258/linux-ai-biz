"""Local pictures for the creator (the owner's choice, 2026-11-01: make them on his own
computer, the desktop's RTX 3060). ComfyUI runs on 127.0.0.1:8188; BAU sends it a picture job,
waits, saves the picture in the media folder with a provenance record, and audits it. Only a
model server on this computer, never anything about minors, an AI record on every file.
Tests use a fake ComfyUI. Written before the code."""

import json
import re
from pathlib import Path

import pytest

from bau.media import comfy

PNG = b"\x89PNG\r\n\x1a\nfake"


class FakeComfy:
    """Answers like ComfyUI's /prompt, /history/{id} and /view (server.py, read 2026-11-01)."""

    def __init__(self, polls_before_done=1):
        self.jobs, self.left = [], polls_before_done

    def __call__(self, req, timeout=0):
        url = req.full_url
        if url.endswith("/prompt"):
            body = json.loads(req.data)
            self.jobs.append(body["prompt"])
            return _Resp({"prompt_id": "p1", "number": 0, "node_errors": {}})
        if "/history/p1" in url:
            if self.left:
                self.left -= 1
                return _Resp({})
            return _Resp({"p1": {"status": {"completed": True, "status_str": "success"},
                                 "outputs": {"7": {"images": [{"filename": "bau_00001_.png",
                                                               "subfolder": "",
                                                               "type": "output"}]}}}})
        if "/view?" in url:
            assert "filename=bau_00001_.png" in url and "type=output" in url
            return _Resp(PNG, raw=True)
        raise AssertionError(url)


class _Resp:
    def __init__(self, data, raw=False):
        self.data = data if raw else json.dumps(data).encode()

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_a_picture_is_drawn_saved_and_recorded(tmp_path):
    fake = FakeComfy()
    out = comfy.draw(tmp_path, "Aria Vale, a fictional adult, autumn cafe, warm light",
                     "aria-mon", seed=7, opener=fake, wait=0,
                     checker=lambda p: {"20-29": 0.9, "10-19": 0.02})   # see test_agecheck
    pic = tmp_path / "artifacts" / "media" / "aria-mon.png"
    assert out["file"] == "aria-mon.png" and pic.read_bytes() == PNG
    prov = json.loads((tmp_path / "artifacts" / "media" / "aria-mon.png.provenance.json")
                      .read_text())
    assert prov["ai_generated"] is True and prov["model"] == comfy.MODEL and prov["seed"] == 7
    graph = fake.jobs[0]
    kinds = {n["class_type"] for n in graph.values()}
    assert kinds == {"CheckpointLoaderSimple", "CLIPTextEncode", "EmptyLatentImage",
                     "KSampler", "VAEDecode", "SaveImage"}
    assert any(n["inputs"].get("text", "").startswith("Aria Vale") for n in graph.values())
    events = [json.loads(x)["event"] for x in
              (tmp_path / "audit" / "chain.jsonl").read_text().splitlines()]
    assert "media.drawn" in events


@pytest.mark.parametrize("prompt", ["a 15-year-old girl at the beach", "schoolgirl outfit"])
def test_nothing_about_minors_is_ever_drawn(tmp_path, prompt):
    fake = FakeComfy()
    with pytest.raises(comfy.ComfyError, match="minors"):
        comfy.draw(tmp_path, prompt, "x", opener=fake, wait=0)
    assert not fake.jobs                                     # never sent to the model


@pytest.mark.parametrize("base", ["http://192.168.1.20:8188", "https://example.com"])
def test_only_a_model_server_on_this_computer(tmp_path, base):
    with pytest.raises(comfy.ComfyError, match="this computer"):
        comfy.draw(tmp_path, "a fictional adult", "x", base=base, opener=FakeComfy(), wait=0)


@pytest.mark.parametrize("name", ["../x", "a/b", ""])
def test_the_file_name_stays_in_the_media_folder(tmp_path, name):
    with pytest.raises(comfy.ComfyError):
        comfy.draw(tmp_path, "a fictional adult", name, opener=FakeComfy(), wait=0)


def test_a_failed_job_says_why(tmp_path):
    class Broken(FakeComfy):
        def __call__(self, req, timeout=0):
            if req.full_url.endswith("/prompt"):
                return _Resp({"error": {"message": "ckpt not found"},
                              "node_errors": {"1": "missing"}})
            return super().__call__(req, timeout)
    with pytest.raises(comfy.ComfyError, match="ckpt not found"):
        comfy.draw(tmp_path, "a fictional adult", "x", opener=Broken(), wait=0)


# Real run in the sandbox (2026-11-01): the creator batch's instruction-style prompt ("keep the
# same identity in every asset") drew a character sheet with colour swatches and a face that
# read young. A picture model gets short visual facts instead, clearly adult and photographic.
def test_the_picture_prompt_is_short_visual_facts_and_clearly_adult():
    profile = {"age": 25, "appearance": ["oval face", "long dark auburn hair"],
               "style": "modern editorial fashion with warm natural light"}
    p = comfy.creator_prompt(profile, "cozy autumn cafe", "portrait")
    assert p.startswith("photo of a 25-year-old adult woman")
    assert "long dark auburn hair" in p and "cozy autumn cafe" in p
    assert "every asset" not in p and "Tier" not in p
    for word in ("childlike", "cartoon", "character sheet", "color swatches"):
        assert word in comfy.NEGATIVE
    with pytest.raises(comfy.ComfyError, match="21"):
        comfy.creator_prompt({**profile, "age": 19}, "x", "portrait")


# ------------------------------------------------------------------ the desktop installer
SETUP = (Path(__file__).resolve().parents[1] / "installer" / "bau-pictures-setup.sh")


def test_pictures_installer_is_pinned_private_and_refuses_the_live_stick():
    text = SETUP.read_text()
    assert re.search(r'COMFY_COMMIT="[0-9a-f]{40}"', text) and "rev-parse" in text
    assert f'MODEL_SHA256="{comfy.MODEL_SHA256}"' in text and "sha256sum" in text
    assert "--listen 127.0.0.1" in text and "0.0.0.0" not in text
    assert "download.pytorch.org/whl/cu126" in text                # driver 550: CUDA 12.x
    assert "/run/live/medium" in text                               # not into RAM
    assert "NoNewPrivileges=yes" in text and "ProtectSystem=strict" in text
    assert "User=comfyui" in text                                   # never root


def test_pictures_installer_ships_on_the_stick():
    mk = (SETUP.parent / "make-payload.sh").read_text()
    assert '"${HERE}/bau-pictures-setup.sh"' in mk


def test_creator_draw_makes_one_picture_per_post(tmp_path, monkeypatch, capsys):
    from bau.cli import main
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    assert main(["creator", "init"]) == 0
    drawn = []
    monkeypatch.setattr(comfy, "draw", lambda home, prompt, name, **k: drawn.append(
        (prompt, name)) or {"file": f"{name}.png", "seed": 1, "bytes": 3})
    assert main(["creator", "draw", str(tmp_path / "creators" / "aria.yaml"),
                 "cozy autumn cafe", "--count", "3"]) == 0
    assert len(drawn) == 3 and all(p.startswith("photo of a 25-year-old adult woman")
                                   for p, _ in drawn)
    assert [n.rsplit("-", 1)[1] for _, n in drawn] == ["1", "2", "3"]
    assert drawn[0][1].startswith("aria-")
