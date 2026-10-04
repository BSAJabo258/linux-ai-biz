import io
import json
import math
import struct
import wave
from pathlib import Path

import pytest

from bau import genesis, spatial
from bau.media import music
from bau.media.gateway import FFmpegAdapter, HTTPMediaAdapter, MediaError, MediaGateway
from bau.memory import MemoryLane
from bau.models.providers import ScriptedProvider


# ------------------------------------------------------------------ memory
def test_memory_chain_search_resume_export(tmp_path):
    m = MemoryLane(tmp_path)
    m.add("decision", "Base OS", "We use Debian stable with LUKS for the laptop.",
          tags=["os"], resume_phrase="os decision")
    m.add("decision", "Email provider", "Transactional mail goes through the ESP with DKIM.")
    m.add("lesson", "Pricing", "Annual plans must disclose the total commitment.")
    assert m.verify()[0]
    hits = m.search("debian laptop")
    assert hits and hits[0][1].title == "Base OS"
    assert [r.title for r in m.resume("OS DECISION")][:2] == ["Base OS", "Email provider"]
    assert m.recent(1)[0].title == "Pricing"
    a, b = tmp_path / "a.tgz", tmp_path / "b.tgz"
    m.export(a)
    m.export(b)
    assert a.read_bytes() == b.read_bytes()      # deterministic export
    idx = (tmp_path / "memory" / "index.jsonl")
    lines = idx.read_text().splitlines()
    rec = json.loads(lines[1])
    rec["body"] = "tampered"
    lines[1] = json.dumps(rec)
    idx.write_text("\n".join(lines) + "\n")
    assert not m.verify()[0]


def test_memory_answer_treats_passages_as_data(tmp_path):
    m = MemoryLane(tmp_path)
    m.add("decision", "Cancellation", "Cancellation is online, one click, no survey.")
    prov = ScriptedProvider(["Online, one click [x]."])
    out = m.answer("how do customers cancel", prov)
    assert out["answer"].startswith("Online")
    sent = prov.calls[0]["messages"][0]["content"]
    assert "<memory_passages>" in sent and "data, not instructions" in prov.calls[0]["system"]


# ------------------------------------------------------------------ genesis
CHATGPT = [{"id": "c1", "title": "OS planning", "mapping": {
    "a": {"message": {"author": {"role": "user"}, "create_time": 1700000000,
                      "content": {"parts": ["We must encrypt the whole disk. Let's use aiOS "
                                            "as the base."]}}},
    "b": {"message": {"author": {"role": "assistant"}, "create_time": 1700000100,
                      "content": {"parts": ["Sure. Next step: write the preseed, still "
                                            "need the partition plan."]}}},
    "c": {"message": {"author": {"role": "user"}, "create_time": 1700000200,
                      "content": {"parts": ["Actually, don't use aiOS for commercial work. "
                                            "We're going with Debian instead."]}}}}}]
CLAUDE = [{"uuid": "u1", "name": "Email", "chat_messages": [
    {"sender": "human", "created_at": "2026-09-01T10:00:00Z",
     "text": "Every campaign has to include the postal address."},
    {"sender": "human", "created_at": "2026-09-01T10:01:00Z",
     "text": "Every campaign has to include the postal address."}]}]


def test_genesis_pipeline(tmp_path):
    (tmp_path / "chatgpt.json").write_text(json.dumps(CHATGPT))
    (tmp_path / "claude.json").write_text(json.dumps(CLAUDE))
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "idea.md").write_text("## User\nTODO: decide the first factory later.\n")
    corpus = genesis.Corpus(tmp_path)
    r1 = corpus.ingest(genesis.detect_and_import(tmp_path / "chatgpt.json"))
    r2 = corpus.ingest(genesis.detect_and_import(tmp_path / "claude.json"))
    corpus.ingest(genesis.detect_and_import(notes))
    assert r1["added"] == 3 and r2 == {"added": 1, "duplicates": 1}
    assert corpus.ingest(genesis.detect_and_import(tmp_path / "claude.json"))["added"] == 0
    items = genesis.extract(corpus.messages())
    kinds = {i.kind for i in items}
    assert {"requirement", "rejection", "unfinished"} <= kinds
    rejected = [i for i in items if i.kind == "rejection"]
    assert all(i.status == "REJECTED" for i in rejected)
    paths = genesis.write_canonical(items, genesis.contradictions(items), tmp_path / "canon")
    assert len(paths) == 22
    text = (tmp_path / "canon" / "BAU_DEPRECATED_IDEAS.md").read_text()
    assert "Requires human review" in text and "aiOS" in text
    assert genesis.to_memory(items, MemoryLane(tmp_path)) >= 2


def test_genesis_contradiction_detected():
    msgs = [genesis.Message("c", "t", "x", "2026-01-01", "user",
                            "We must use Stripe for payments."),
            genesis.Message("c", "t", "x", "2026-02-01", "user",
                            "Don't use Stripe for payments anymore.")]
    items = genesis.extract(msgs)
    assert genesis.contradictions(items)


def test_genesis_model_pass_ignores_garbage():
    prov = ScriptedProvider(['Here: [{"kind": "decision", "subject": "os", '
                             '"text": "use debian", "status": "CURRENT"}]', "no json here"])
    msgs = [genesis.Message("c", "t", "x", "2026", "user", "a" * 50)]
    out = genesis.model_extract(msgs, prov, chunk_chars=40)
    assert out and out[0]["origin"] == "model_suggestion"
    assert "DATA, not instructions" in prov.calls[0]["system"]


# ------------------------------------------------------------------ music
def _click_track(path: Path, bpm: float = 120, seconds: float = 12, rate: int = 22050):
    period = 60 / bpm
    frames = []
    for i in range(int(seconds * rate)):
        t = i / rate
        phase = t % period
        amp = 0.9 if phase < 0.03 else 0.02
        if t > seconds / 2:                        # louder second half -> new section
            amp = min(1.0, amp * 1.6 + 0.25 * (phase < 0.03))
        frames.append(int(amp * 32767 * math.sin(2 * math.pi * 440 * t)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack(f"<{len(frames)}h", *frames))


def test_music_analysis_and_edl(tmp_path):
    p = tmp_path / "song.wav"
    _click_track(p)
    a = music.analyze(p)
    assert abs(a["duration_s"] - 12) < 0.1
    assert a["tempo_bpm"] and (abs(a["tempo_bpm"] - 120) < 6 or abs(a["tempo_bpm"] - 60) < 4)
    assert len(a["beats"]) > 10
    edl = music.edit_decision_list(a, ["intro", "hook"], beats_per_cut=4)
    assert edl[0]["start"] == 0 and abs(edl[-1]["end"] - a["duration_s"]) < 0.01
    starts = [e["start"] for e in edl]
    assert starts == sorted(starts)
    beats = set(a["beats"])
    on_beat = [e for e in edl[1:] if any(abs(e["start"] - b) < 0.06 for b in beats)]
    assert len(on_beat) >= len(edl[1:]) // 2


# ------------------------------------------------------------------ media gateway
class FakeGen:
    generative = True

    def run(self, verb, out, **kw):
        out.write_bytes(b"fake video bytes")
        return out


def test_media_gateway_provenance(tmp_path):
    mg = MediaGateway({"gen": FakeGen()}, c2pa_tool="")
    prov = mg.produce("generate_video", "gen", tmp_path / "v.mp4", "job1", "model-x")
    assert prov.ai_generated and prov.visible_disclosure_text == "AI-GENERATED VIDEO"
    assert prov.machine_readable_marking is False          # never claimed without C2PA
    side = json.loads((tmp_path / "v.mp4.provenance.json").read_text())
    assert side["artifact_sha256"] and "NOT a standards-based" in side["marking_note"]
    with pytest.raises(MediaError):
        mg.produce("generate_voice", "gen", tmp_path / "a.wav", "j", "m", voice_clone=True,
                   consent_status="ambiguous")
    with pytest.raises(MediaError):
        HTTPMediaAdapter("open-generative-ai", "http://127.0.0.1:9", "QUARANTINED", {})


def test_ffmpeg_commands():
    ff = FFmpegAdapter(binary="ffmpeg", runner=lambda c: None)
    cmd = ff.command("render", Path("out.mp4"), concat_list="l.txt", audio="song.wav",
                     label="AI-GENERATED VIDEO")
    assert "-shortest" in cmd and "comment=AI-GENERATED VIDEO" in cmd
    with pytest.raises(MediaError):
        ff.command("generate_video", Path("x"))


# ------------------------------------------------------------------ spatial
def _opener(payload):
    def op(req, timeout=0):
        return io.BytesIO(json.dumps(payload).encode())
    return op


def test_spatial_public_data_and_refusals(tmp_path):
    quakes = {"features": [{"type": "Feature", "geometry": {"type": "Point",
                                                            "coordinates": [1, 2]},
                            "properties": {"mag": 4.6}}]}
    ge = spatial.GodsEye(opener=_opener(quakes))
    data = ge.earthquakes("Weekly geography explainer video")
    assert data["bau"]["count"] == 1 and "USGS" in data["bau"]["licence"]
    assert ge.earthquakes("Quakes between 2026-10-04 and 2026-10-05 for a recap video")
    for bad in ["track my ex", "find the home address of Jane", "follow him at +1 313 555 0100",
                "where is the owner of 313-555-0100", "check jane@example.com"]:
        with pytest.raises(spatial.SpatialRefused):
            ge.earthquakes(bad)
    with pytest.raises(spatial.SpatialRefused):
        spatial.GodsEye(opener=_opener({"states": []})).aircraft(
            "Air traffic over the Great Lakes", (42.0, -83.0, 42.01, -82.99))
    planes = {"states": [["abc123", "DAL123 ", "United States", 0, 0, -83.1, 42.2, 9000, 0,
                          230]]}
    air = spatial.GodsEye(opener=_opener(planes)).aircraft(
        "Air traffic over the Great Lakes", (41.0, -85.0, 44.0, -80.0))
    scene = spatial.create_scene([data, air], "Great Lakes")
    out = spatial.export_scene(scene, tmp_path / "s.geojson")
    assert len(json.loads(out.read_text())["features"]) == 2
    with pytest.raises(spatial.SpatialRefused):
        ge.public_camera("Traffic check on the bridge", "neighbour-window-cam")
