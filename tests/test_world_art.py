"""The world's characters are real art files (docs/visual/VISUAL_ART_DIRECTION.md): a sprite
sheet built by scripts/world_sprites.py, served only from a fixed list of paths."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "src" / "bau" / "ui" / "world"


def sprites():
    spec = importlib.util.spec_from_file_location("world_sprites",
                                                  ROOT / "scripts" / "world_sprites.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_committed_sheet_is_what_the_script_draws():
    pytest.importorskip("PIL")
    from PIL import Image
    sheet, meta = sprites().build()
    assert json.loads((ART / "characters.json").read_text()) == json.loads(json.dumps(meta))
    on_disk = Image.open(ART / "characters.png").convert("RGBA")
    assert on_disk.size == sheet.size and on_disk.tobytes() == sheet.tobytes()


def test_every_character_has_every_animation_and_its_own_look():
    meta = json.loads((ART / "characters.json").read_text())
    w, h = meta["frame"]
    assert set(meta["characters"]) == {"jarvis", "researcher", "producer", "engineer"}
    for who, c in meta["characters"].items():
        assert set(c["animations"]) == {"idle", "walk_front", "walk_back", "work", "wait",
                                        "blocked", "done"}, who
        assert c["role"]
    pytest.importorskip("PIL")
    from PIL import Image
    im = Image.open(ART / "characters.png").convert("RGBA")
    rows = {who: im.crop((0, c["animations"]["work"]["row"] * h, w * 4,
                          (c["animations"]["work"]["row"] + 1) * h)).tobytes()
            for who, c in meta["characters"].items()}
    assert len(set(rows.values())) == len(rows)            # no two characters drawn the same


def test_the_page_gets_the_sheet_and_nothing_else(tmp_path):
    import http.client
    import threading

    from test_assistant import make

    from bau.assistant import Voice
    from bau.ui.jarvis_server import serve
    srv, key = serve(make(tmp_path), Voice(tmp_path), 0, key="k" * 24)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        port = srv.server_address[1]

        def get(path):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            c.request("GET", path, headers={"Host": f"127.0.0.1:{port}"})
            r = c.getresponse()
            return r.status, r.getheader("Content-Type"), r.read()
        st, kind, body = get("/world/characters.png")
        assert st == 200 and kind == "image/png" and body[:4] == b"\x89PNG"
        assert get("/world/characters.json")[0] == 200
        assert get("/world/../jarvis_server.py")[0] == 404
        assert get("/world/other.png")[0] == 404
    finally:
        srv.shutdown()
