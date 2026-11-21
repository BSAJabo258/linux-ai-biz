"""Her clips (the owner's ask 2026-11-21): one of her kept explicit pictures brought to life by
Wan 2.2 in the desktop's ComfyUI, every frame age-checked, her alone and within Fanvue's rules
(read 2026-11-21: no second person, no bodily fluids), posted to Fanvue levels 2 and 3 at the
owner's clip price. Fakes only: no ComfyUI, no ffmpeg, no Fanvue."""

import hashlib
import json

import pytest
import yaml
from test_fanvue import FakeFanvue, client

from bau import creator_feed as CF
from bau import fanvue as F
from bau.media import comfy

MP4 = b"\x00\x00\x00\x18ftypmp42fake-clip"


class FakeComfy:
    """ComfyUI's /upload/image, /prompt, /history, /queue and /view for one clip job."""

    def __init__(self):
        self.jobs, self.uploads = [], []

    def __call__(self, req, timeout=0):
        url = req.full_url
        if url.endswith("/upload/image"):
            self.uploads.append(req.data)
            return _Resp({"name": "bau-clip-x.png", "subfolder": ""})
        if url.endswith("/prompt"):
            self.jobs.append(json.loads(req.data)["prompt"])
            return _Resp({"prompt_id": "c1", "node_errors": {}})
        if "/history/c1" in url:
            return _Resp({"c1": {"status": {"status_str": "success"}, "outputs": {"12": {
                "images": [{"filename": "clip_00001_.mp4", "subfolder": "bau",
                            "type": "output"}], "animated": [True]}}}})
        if url.endswith("/queue"):
            return _Resp({"queue_running": [], "queue_pending": []})
        if "/view?" in url:
            assert "filename=clip_00001_.mp4" in url
            return _Resp(MP4, raw=True)
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


def kept(home, name="her.png", lane="explicit", passed=True):
    media = home / "artifacts" / "media"
    media.mkdir(parents=True, exist_ok=True)
    data = b"\x89PNG-her-" + name.encode()
    (media / name).write_bytes(data)
    (media / f"{name}.provenance.json").write_text(json.dumps({
        "ai_generated": True, "lane": lane, "file_sha256": hashlib.sha256(data).hexdigest(),
        "age_check": {"passed": passed}}))
    return name


FRAMES = 5                     # a short test clip: 4k+1 frames, as Wan makes them


def frames(n=FRAMES):
    def get(clip, out):
        out.mkdir(parents=True, exist_ok=True)
        files = []
        for i in range(n):
            f = out / f"f{i}.png"
            f.write_bytes(b"frame")
            files.append(f)
        return files
    return get


def scores(young):
    seq = list(young)
    return lambda path: {"10-19": seq.pop(0), "20-29": 0.9}


def run(home, prompt="she slowly points her bare feet toward the camera", **kw):
    fake = FakeComfy()
    out = comfy.animate(home, kw.pop("picture", kept(home)), prompt, "clip-1", opener=fake,
                        wait=0.001, frames_of=kw.pop("frames_of", frames()),
                        checker=kw.pop("checker", scores([0.01, 0.02, 0.03, 0.01, 0.02])),
                        frames=FRAMES, **kw)
    return out, fake


def test_comfyuis_own_wan_workflow_starting_from_her_picture():
    g = comfy.wan_graph("bau-clip-x.png", "she smiles", 7)
    kinds = {n["class_type"] for n in g.values()}
    assert {"UNETLoader", "ModelSamplingSD3", "CLIPLoader", "CLIPTextEncode", "VAELoader",
            "LoadImage",
            "Wan22ImageToVideoLatent", "KSampler", "VAEDecode", "CreateVideo",
            "SaveVideo"} == kinds
    assert g["3"]["inputs"]["type"] == "wan" and g["2"]["inputs"]["shift"] == 8
    assert g["8"]["inputs"]["start_image"] == ["7", 0] and g["7"]["inputs"]["image"] == \
        "bau-clip-x.png"
    assert (g["8"]["inputs"]["length"] - 1) % 4 == 0
    with pytest.raises(comfy.ComfyError):
        comfy.wan_graph("x.png", "p", 1, frames=72)              # Wan needs 4k+1 frames


def test_a_clip_whose_every_frame_passes_is_kept_with_its_record(tmp_path):
    out, fake = run(tmp_path)
    clip = tmp_path / "artifacts" / "media" / "clip-1.mp4"
    assert out["file"] == "clip-1.mp4" and clip.read_bytes() == MP4
    prov = json.loads((tmp_path / "artifacts/media/clip-1.mp4.provenance.json").read_text())
    assert prov["ai_generated"] and prov["model"] == comfy.WAN and prov["lane"] == "explicit"
    assert prov["age_check"]["passed"] and prov["age_check"]["frames"] == FRAMES
    assert prov["age_check"]["of_frames"] == FRAMES                  # every frame, none skipped
    assert prov["file_sha256"] == hashlib.sha256(MP4).hexdigest()
    assert prov["start"]["file"] == "her.png"
    assert fake.uploads and fake.jobs[0]["8"]["class_type"] == "Wan22ImageToVideoLatent"
    rows = [json.loads(x) for x in (tmp_path / "audit/chain.jsonl").read_text().splitlines()]
    assert any(r.get("event") == "media.animated" for r in rows)
    assert not list((tmp_path / "artifacts" / "rejected").glob(".frames-*"))   # cleaned up


def test_one_young_looking_frame_keeps_nothing(tmp_path):
    with pytest.raises(comfy.ComfyError, match="under 20"):
        run(tmp_path, checker=scores([0.01, 0.01, 0.01, 0.4, 0.01]))
    assert not (tmp_path / "artifacts" / "media" / "clip-1.mp4").exists()
    assert (tmp_path / "artifacts" / "rejected" / "clip-1.mp4").exists()


def test_a_clip_with_a_frame_missing_keeps_nothing(tmp_path):
    # The security review, 2026-11-21: frames left unchecked could hide a young-looking one.
    with pytest.raises(comfy.ComfyError, match="frames decoded"):
        run(tmp_path, frames_of=frames(FRAMES - 1))
    assert not (tmp_path / "artifacts" / "media" / "clip-1.mp4").exists()


def test_the_frames_are_scored_in_one_run_of_the_age_model(tmp_path, monkeypatch):
    calls = []

    def many(paths):
        calls.append(len(paths))
        return [{"10-19": 0.01, "20-29": 0.9}] * len(paths)
    monkeypatch.setattr(comfy, "age_scores_many", many)
    run(tmp_path, checker=None)
    assert calls == [FRAMES]


def test_an_age_check_that_cannot_run_keeps_nothing(tmp_path):
    def broken(path):
        raise OSError("the age model did not run")
    with pytest.raises(comfy.ComfyError, match="could not run"):
        run(tmp_path, checker=broken)
    assert not (tmp_path / "artifacts" / "media" / "clip-1.mp4").exists()


@pytest.mark.parametrize("prompt", [
    "a man finishes on her chest", "creampie close-up", "she is squirting", "facial",
    "her boyfriend joins", "a couple on the bed", "choking her", "she is asleep",
    "stepsister scene", "cum on her", "two people kiss"])
def test_clips_are_her_alone_and_within_fanvues_rules(tmp_path, prompt):
    with pytest.raises(comfy.ComfyError, match="alone"):
        run(tmp_path, prompt=prompt)
    assert not (tmp_path / "artifacts" / "media" / "clip-1.mp4").exists()


def test_never_anything_about_minors(tmp_path):
    with pytest.raises(comfy.ComfyError, match="minors"):
        run(tmp_path, prompt="a teen girl smiles")


def test_only_from_her_kept_age_checked_pictures(tmp_path):
    with pytest.raises(comfy.ComfyError, match="kept pictures"):
        run(tmp_path, picture=kept(tmp_path, "no.png", passed=False))
    with pytest.raises(comfy.ComfyError, match="kept pictures"):
        run(tmp_path, picture="missing.png")


def test_the_prompt_librarys_clip_lines_pass_both_guards():
    from bau.virtual_creator import MINOR_REFERENCE
    c = CF.clips()
    lines = [x for k in ("feet", "solo") for x in c[k]["motion"]] + c["camera"]
    assert lines and not [x for x in lines if comfy.SOLO_ONLY.search(x)
                          or MINOR_REFERENCE.search(x)]
    assert {c["feet"]["level"], c["solo"]["level"]} <= {2, 3}


def test_fanvue_gets_a_clip_as_video_and_only_on_levels_2_and_3(tmp_path):
    media = tmp_path / "artifacts" / "media"
    media.mkdir(parents=True)
    (media / "c.mp4").write_bytes(MP4)
    (media / "c.mp4.provenance.json").write_text(json.dumps({
        "ai_generated": True, "lane": "explicit", "file_sha256": hashlib.sha256(MP4).hexdigest(),
        "age_check": {"passed": True}}))
    q = F.Queue(tmp_path)
    assert "clips are for levels 2 and 3 only" in q.check("c.mp4", "x", 0)
    assert not q.check("c.mp4", "x", 2, price_cents=1499)
    fake = FakeFanvue()
    client(tmp_path, fake).upload_image(media / "c.mp4")
    started = next(b for m, u, h, b in fake.calls if u.endswith("/v1/media/uploads") and m ==
                   "POST")
    assert json.loads(started)["mediaType"] == "video"


def profile(home, clip=19.99):
    (home / "creators").mkdir(parents=True, exist_ok=True)
    prices = {"subscription": 9.99, "nude": 14.99, "xxx": 29.99}
    if clip:
        prices["clip"] = clip
    (home / "creators" / "aria.yaml").write_text(yaml.safe_dump({
        "id": "aria", "age": 27, "explicit_boundaries": ["No animals"], "prices": prices}))


def ready(monkeypatch, wan=True):
    monkeypatch.setattr(comfy, "chroma_ready", lambda: True)
    monkeypatch.setattr(comfy, "wan_ready", lambda: wan)


def test_clips_wait_for_the_model_her_picture_and_his_price(tmp_path, monkeypatch):
    ready(monkeypatch)
    profile(tmp_path, clip=None)
    kept(tmp_path)
    prof = CF._profile(tmp_path)[1]
    assert not CF.clips_ready(tmp_path, prof)                   # no clip price yet
    profile(tmp_path)
    prof = CF._profile(tmp_path)[1]
    assert CF.clips_ready(tmp_path, prof)
    ready(monkeypatch, wan=False)
    assert not CF.clips_ready(tmp_path, prof)                   # Wan 2.2 not installed


def test_a_clip_job_queues_her_clip_at_his_price_for_his_review(tmp_path, monkeypatch):
    ready(monkeypatch)
    profile(tmp_path)
    kept(tmp_path)
    seen = {}

    def animate(home, start, prompt, name, negative=""):
        seen.update(start=start, prompt=prompt, negative=negative)
        media = home / "artifacts" / "media"
        (media / f"{name}.mp4").write_bytes(MP4)
        (media / f"{name}.mp4.provenance.json").write_text(json.dumps({
            "ai_generated": True, "lane": "explicit",
            "file_sha256": hashlib.sha256(MP4).hexdigest(), "age_check": {"passed": True}}))
        return {"file": f"{name}.mp4"}
    task = {"detail": {"job": "fanvue_clip", "kind": "feet", "level": 2,
                       "motion": "she slowly points her bare feet", "camera": "static camera"}}
    out = CF.make_clip(tmp_path, task, animate=animate)
    assert out["ok"] and "waiting for the owner" in out["evidence"]
    item = F.Queue(tmp_path).items()[0]
    assert item["status"] == "REVIEW" and item["price_cents"] == 1999 and item["level"] == 2
    assert item["picture"].endswith(".mp4") and F.AI_LABEL in item["caption"]
    assert seen["start"] == "her.png" and "animals" in seen["negative"]   # his limits


def test_the_feed_makes_at_most_one_clip_a_day_among_his_posts(tmp_path, monkeypatch):
    ready(monkeypatch)
    profile(tmp_path)
    kept(tmp_path)
    from bau import autopilot as A
    F.set_autopost(tmp_path, True, "human:owner", "subscribers", 3)
    assert CF.fill(tmp_path) == 3
    jobs = [t["detail"]["job"] for t in A._load(tmp_path)["tasks"]]
    assert sorted(jobs) == ["fanvue_clip", "fanvue_post", "fanvue_post"]
    st = A._load(tmp_path)                               # the day's work is done...
    st["tasks"] = [dict(t, state="done") for t in st["tasks"]]
    A._save(tmp_path, st)
    assert CF.fill(tmp_path) == 3                        # ...more posts, no second clip today
    jobs = [t["detail"]["job"] for t in A._load(tmp_path)["tasks"]]
    assert jobs.count("fanvue_clip") == 1


def test_the_video_setup_never_writes_as_root_in_comfyuis_folder():
    # The security review, 2026-11-21: the folder is the comfyui account's, so root following a
    # link planted there could change a system file. Every write there runs as comfyui.
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "installer" / "bau-video-setup.sh").read_text()
    body = text.split('for entry in "${FILES[@]}"; do', 1)[1].split("\ndone", 1)[0]
    for line in body.splitlines():
        cmd = line.strip()
        if cmd.startswith(("mkdir", "install", "mv ", "rm ", "chown", "chmod", "cp ")) or \
                cmd.startswith(("|| { rm", "curl")):
            raise AssertionError(f"runs as root in comfyui's folder: {cmd}")
    assert body.count("as_comfy") >= 6 and "install -" not in body
