"""The creator's locked face: candidates are drawn out of the posting folder, only the owner
locks one, the lock is checked by SHA-256, and only the sfw lane is drawn from it."""

from __future__ import annotations

import json

import pytest

from bau import face
from bau.media import comfy

PROF = {"id": "aria", "name": "Aria", "age": 25, "appearance": ["long black hair"]}


def fake_draw(calls):
    def draw(home, prompt, name, **kw):
        calls.append((prompt, name, kw))
        media = home / "artifacts" / "media"
        media.mkdir(parents=True, exist_ok=True)
        (media / f"{name}.png").write_bytes(name.encode())
        return {"file": f"{name}.png"}
    return draw


def test_candidates_never_stay_where_the_fanvue_queue_looks(tmp_path):
    calls = []
    out = face.draw_candidates(tmp_path, PROF, 3, drawer=fake_draw(calls))
    assert [o["number"] for o in out] == [1, 2, 3]
    assert not list((tmp_path / "artifacts" / "media").glob("*.png"))
    assert [p.name for p in face.candidates(tmp_path, PROF)] == ["aria-1.png", "aria-2.png",
                                                                  "aria-3.png"]
    assert "25-year-old adult woman" in calls[0][0] and "head and shoulders" in calls[0][0]
    more = face.draw_candidates(tmp_path, PROF, 1, drawer=fake_draw(calls))
    assert more[0]["number"] == 4                         # never overwrites one you saw


def test_only_the_owner_locks_and_a_changed_file_is_not_used(tmp_path):
    face.draw_candidates(tmp_path, PROF, 2, drawer=fake_draw([]))
    with pytest.raises(PermissionError):
        face.pick(tmp_path, PROF, 1, "agent:jarvis")
    with pytest.raises(face.FaceError, match="no candidate 9"):
        face.pick(tmp_path, PROF, 9, "human:owner")
    lock = face.pick(tmp_path, PROF, 2, "human:owner")
    assert face.locked(tmp_path, PROF).read_bytes() == b"face-aria-2"
    assert json.loads((tmp_path / "creators" / "faces" / "aria.lock.json").read_text()) == lock
    face.locked(tmp_path, PROF).write_bytes(b"someone else")
    assert face.locked(tmp_path, PROF) is None
    assert face.status(tmp_path, PROF)["changed_since_lock"] is True


def test_a_bad_profile_id_is_refused(tmp_path):
    with pytest.raises(face.FaceError):
        face.draw_candidates(tmp_path, {"id": "../x", "age": 25}, 1, drawer=fake_draw([]))
    assert face.locked(tmp_path, {"id": "../x"}) is None


def test_the_face_nodes_replace_the_model_only_when_a_face_is_given():
    plain = comfy.graph("p", 1)
    assert "10" not in plain and plain["5"]["inputs"]["model"] == ["1", 0]
    g = comfy.graph("p", 1, face="bau-face-x.png")
    assert g["8"] == {"class_type": "LoadImage", "inputs": {"image": "bau-face-x.png"}}
    assert g["9"]["inputs"]["preset"] == "PLUS FACE (portraits)"
    assert g["10"]["class_type"] == "IPAdapterAdvanced" and g["5"]["inputs"]["model"] == ["10", 0]


class Resp:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.body


def test_draw_uploads_the_face_and_records_it_on_the_sfw_lane_only(tmp_path):
    f = tmp_path / "aria.png"
    f.write_bytes(b"the face")
    sent = []

    def opener(req, timeout=60):
        url = req.full_url
        sent.append((url, req.data))
        if url.endswith("/upload/image"):
            return Resp(json.dumps({"name": "bau-face-1.png", "subfolder": ""}).encode())
        if url.endswith("/prompt"):
            return Resp(json.dumps({"prompt_id": "p1"}).encode())
        if "/history/" in url:
            return Resp(json.dumps({"p1": {"outputs": {"7": {"images": [
                {"filename": "a.png", "subfolder": "", "type": "output"}]}}}}).encode())
        return Resp(b"PNG")

    comfy.draw(tmp_path, "photo of a 25-year-old adult woman", "pic-1", opener=opener,
               checker=lambda p: {"20-29": 1.0}, face=f)
    graph = json.loads(next(d for u, d in sent if u.endswith("/prompt")))["prompt"]
    assert graph["8"]["inputs"]["image"] == "bau-face-1.png"
    assert b"the face" in next(d for u, d in sent if u.endswith("/upload/image"))
    prov = json.loads((tmp_path / "artifacts" / "media" / "pic-1.png.provenance.json")
                      .read_text())
    assert prov["face_lock"]["face_sha256"] and prov["lane"] == "sfw"
    sent.clear()
    comfy.draw(tmp_path, "photo of a 25-year-old adult woman", "pic-2", opener=opener,
               checker=lambda p: {"20-29": 1.0}, face=f, lane="explicit")
    assert not any(u.endswith("/upload/image") for u, _ in sent)   # no face lock on Chroma


def test_the_setup_script_ships_with_the_package():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert (root / "installer/bau-face-setup.sh").read_text() == \
        (root / "src/bau/data/setup/bau-face-setup.sh").read_text()
