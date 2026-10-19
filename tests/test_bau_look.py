"""The BAU look: the owner's own art behind Jarvis and Mission Control, gently alive, and
the stick's desktop, login screen and dark theme in the same colours. Cheap on an 8 GB
laptop: still images with light CSS animation (no video wallpaper), paused for
reduced-motion users. The owner can add their own images (`bau look add`). Written
before the code."""

import json
import re
import shutil
import subprocess
import threading
import urllib.request
from importlib import resources
from pathlib import Path

import pytest

from bau import cli
from bau import look as L
from bau.accessibility import lint_html

ROOT = Path(__file__).resolve().parents[1]
CONF = ROOT / "image" / "live-build" / "config"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


# ------------------------------------------------------------------ the art and the choice

def test_shipped_art_and_wallpapers():
    art = resources.files("bau.ui") / "art"
    for name in [f"{n}.jpg" for n in L.SHIPPED] + [f"wall-{n}.jpg" for n in L.SHIPPED]:
        assert (art / name).read_bytes()[:3] == b"\xff\xd8\xff", name
    pil = pytest.importorskip("PIL.Image")
    with pil.open(str(art / "wall-moon.jpg")) as im:
        assert im.size == (1920, 1080)


def test_default_is_the_moon_and_alive(tmp_path):
    got = L.show(tmp_path)
    assert got["art"] == "moon" and got["alive"] is True
    assert {"moon", "light", "watercolor", "gold", "earth", "none"} <= set(got["choices"])


def test_owner_picks_the_art_and_can_switch_it_off(tmp_path):
    assert L.set_look(tmp_path, art="light")["art"] == "light"
    assert L.art_file(tmp_path)[0].read_bytes()[:3] == b"\xff\xd8\xff"
    assert L.set_look(tmp_path, alive=False)["alive"] is False
    L.set_look(tmp_path, art="none")
    assert L.art_file(tmp_path) is None
    with pytest.raises(ValueError):
        L.set_look(tmp_path, art="nope")


def test_owner_adds_their_own_images(tmp_path):
    src = tmp_path / "My Phoenix Art!.PNG"
    src.write_bytes(PNG)
    name = L.add(tmp_path, src)
    assert name == "my-phoenix-art"
    assert (tmp_path / "art" / "my-phoenix-art.png").read_bytes() == PNG
    assert L.show(tmp_path)["art"] == "my-phoenix-art"          # used at once
    f, ctype = L.art_file(tmp_path)
    assert ctype == "image/png" and f.read_bytes() == PNG


def test_only_real_images_of_sane_size_come_in(tmp_path):
    bad = tmp_path / "script.jpg"
    bad.write_text("#!/bin/sh\nrm -rf /\n")
    with pytest.raises(ValueError, match="JPEG or PNG"):
        L.add(tmp_path, bad)
    big = tmp_path / "huge.jpg"
    big.write_bytes(JPEG + b"\x00" * (L.MAX_BYTES + 1))
    with pytest.raises(ValueError, match="too big"):
        L.add(tmp_path, big)
    ok = tmp_path / "a.jpg"
    ok.write_bytes(JPEG)
    assert L.add(tmp_path, ok, name="../../etc/passwd") == "etc-passwd"


# ------------------------------------------------------------------ Jarvis shows it

@pytest.fixture
def jarvis(tmp_path):
    from test_jarvis_live import make

    from bau.assistant import Voice
    from bau.ui.jarvis_server import serve
    srv, _ = serve(make(tmp_path), Voice(tmp_path), 0, key="k123")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield tmp_path, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_jarvis_serves_the_art_and_tells_the_page(jarvis):
    home, url = jarvis
    with urllib.request.urlopen(url + "/art") as r:
        assert r.headers["Content-Type"] == "image/jpeg"
        assert r.read()[:3] == b"\xff\xd8\xff"
    req = urllib.request.Request(url + "/api/state", headers={"X-Jarvis-Key": "k123"})
    with urllib.request.urlopen(req) as r:
        assert "img-src 'self'" in r.headers["Content-Security-Policy"]
        assert json.loads(r.read())["look"] == {"art": "moon", "alive": True}
    L.set_look(home, art="none")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(url + "/art")
    assert e.value.code == 404


def test_the_page_brings_the_art_to_life_calmly():
    page = (resources.files("bau.ui") / "jarvis.html").read_text()
    assert 'id="art"' in page and "url(/art" in page
    assert "@keyframes breathe" in page and "@keyframes rise" in page
    assert re.search(r"prefers-reduced-motion[^{]*\{[^}]*#art", page)
    assert "document.body.dataset.state" in page           # thinking makes it glow faster
    assert 'body[data-state="thinking"]' in page
    assert lint_html(page) == []


# ------------------------------------------------------------------ Mission Control too

def test_mission_control_serves_the_art_and_its_choice(tmp_path):
    from bau.ui.server import _api, serve
    assert _api("/api/look", tmp_path) == {"art": "moon", "alive": True}
    srv = serve(0, tmp_path)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/art") as r:
            assert r.headers["Content-Type"] == "image/jpeg"
            assert "img-src 'self'" in r.headers["Content-Security-Policy"]
    finally:
        srv.shutdown()
    page = (resources.files("bau.ui") / "page.html").read_text()
    assert 'id="art"' in page and "/api/look" in page and lint_html(page) == []


# ------------------------------------------------------------------ the command

def test_cli_look(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    assert cli.main(["look", "set", "light"]) == 0
    assert json.loads(capsys.readouterr().out)["art"] == "light"
    assert cli.main(["look", "alive", "off"]) == 0
    assert json.loads(capsys.readouterr().out)["alive"] is False
    img = tmp_path / "mine.jpg"
    img.write_bytes(JPEG)
    assert cli.main(["look", "add", str(img)]) == 0
    assert json.loads(capsys.readouterr().out)["art"] == "mine"


# ------------------------------------------------------------------ the stick's desktop

DESKTOP = CONF / "includes.chroot" / "usr" / "local" / "bin" / "bau-look-desktop"


def test_stick_puts_the_art_on_the_desktop_and_login_screen():
    hook = (CONF / "hooks" / "live" / "0500-bau.hook.chroot").read_text()
    assert "/usr/share/backgrounds/bau" in hook and '"${art}"/wall-*.jpg' in hook
    greeter = (CONF / "includes.chroot" / "etc" / "lightdm" / "lightdm-gtk-greeter.conf.d" /
               "50-bau.conf").read_text()
    assert "background=/usr/share/backgrounds/bau/wall-moon.jpg" in greeter
    assert "theme-name=Adwaita-dark" in greeter
    auto = (CONF / "includes.chroot" / "etc" / "xdg" / "autostart" /
            "bau-look.desktop").read_text()
    assert "Exec=/usr/local/bin/bau-look-desktop" in auto


def test_desktop_look_is_set_once_and_never_overrides_the_owners_choice():
    text = DESKTOP.read_text()
    assert "look-applied" in text                     # a marker: only the first login
    assert "last-image" in text and "backdrop-cycle-enable" in text
    assert "Adwaita-dark" in text


@pytest.mark.skipif(not shutil.which("shellcheck"), reason="needs shellcheck")
def test_shellcheck():
    r = subprocess.run(["shellcheck", str(DESKTOP)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
