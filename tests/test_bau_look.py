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
    for name in [f"{n}.jpg" for n in L.SHIPPED] + [f"wall-{n}.jpg" for n in L.LIVE]:
        assert (art / name).read_bytes()[:3] == b"\xff\xd8\xff", name
    assert not (art / "wall-moon.jpg").is_file()        # the owner did not like the inkblots
    pil = pytest.importorskip("PIL.Image")
    for n in L.LIVE:
        with pil.open(str(art / f"wall-{n}.jpg")) as im:
            assert im.size == (1920, 1080)


def test_default_is_the_anime_dusk_and_alive(tmp_path):
    got = L.show(tmp_path)
    assert got["art"] == "dusk" and got["alive"] is True
    assert {"dusk", "summer", "moon", "light", "watercolor", "gold", "earth", "none"} <= \
        set(got["choices"])


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
        look = json.loads(r.read())["look"]
        assert look["art"] == "dusk" and look["alive"] is True
        assert look["flow"] == list(L.LIVE) and look["live"] == list(L.LIVE)
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


# ------------------------------------------------------------------ liquid: the art melts

def test_the_flow_starts_with_the_chosen_art_and_holds_the_rest(tmp_path):
    assert L.brief(tmp_path)["flow"] == list(L.LIVE)                # the live scenes
    L.set_look(tmp_path, art="gold")
    assert L.brief(tmp_path)["flow"][0] == "gold"
    L.set_look(tmp_path, flow=["earth", "moon"])
    assert L.brief(tmp_path)["flow"] == ["gold", "earth", "moon"]   # the chosen one leads
    assert L.show(tmp_path)["flow"] == ["earth", "moon"]
    with pytest.raises(ValueError):
        L.set_look(tmp_path, flow=["moon", "nope"])
    L.set_look(tmp_path, flow=[])                                       # empty = the default
    assert L.show(tmp_path)["flow"] == list(L.LIVE)
    L.set_look(tmp_path, art="none")
    assert L.brief(tmp_path) == {"art": None, "alive": True, "flow": [], "live": list(L.LIVE)}


def test_owner_art_joins_the_flow(tmp_path):
    src = tmp_path / "phoenix.jpg"
    src.write_bytes(JPEG)
    L.add(tmp_path, src)
    assert L.brief(tmp_path)["flow"][0] == "phoenix"
    assert "phoenix" in L.show(tmp_path)["flow"]
    f, ctype = L.art_named(tmp_path, "phoenix")
    assert ctype == "image/jpeg" and f.read_bytes() == JPEG
    assert L.art_named(tmp_path, "none") is None
    assert L.art_named(tmp_path, "../../etc/passwd") is None


def test_jarvis_serves_each_picture_of_the_flow(jarvis):
    _, url = jarvis
    for name in L.SHIPPED:
        with urllib.request.urlopen(f"{url}/art/{name}") as r:
            assert r.headers["Content-Type"] == "image/jpeg"
            assert r.read()[:3] == b"\xff\xd8\xff"
    for bad in ("nope", "..%2F..%2Fetc%2Fpasswd", "none"):
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"{url}/art/{bad}")
        assert e.value.code == 404


def test_the_page_melts_the_pictures_into_each_other_cheaply():
    page = (resources.files("bau.ui") / "jarvis.html").read_text()
    assert '<canvas id="liquid"' in page
    assert 'getContext("webgl"' in page                     # the GPU does the melting
    assert "/art/" in page and "look.flow" in page          # every picture of the flow
    assert "visibilitychange" in page                       # stops when not on screen
    assert "LIQUID_SCALE" in page                           # drawn at part resolution
    assert "LIQUID_FPS" in page                             # and at a capped frame rate
    assert "uEnergy" in page and "uLevel" in page           # moves with Jarvis's state and voice
    m = re.search(r"if \(REDUCED \|\| !gl\)", page)      # still picture without GPU or motion
    assert m, "needs the still fallback"
    assert "webglcontextlost" in page


def test_the_core_is_a_glass_drop_that_breathes_the_pictures():
    page = (resources.files("bau.ui") / "jarvis.html").read_text()
    assert "uCore" in page and "CORE = [X, Y, R]" in page     # the glass sits where the orb is
    assert "fres" in page and "rot(uMix" in page              # rim light; the vortex in and out
    assert "if (!LIQ)" in page                                # the 2D orb lets the glass show
    assert "texture2DLod" in page and "gl.POINTS" in page     # embers from the picture's colours
    assert "MAX_VERTEX_TEXTURE_IMAGE_UNITS" in page           # and only where the GPU can
    assert "EMBERS = " in page and "% 3600" in page           # few of them; time kept small


def test_the_liquid_art_never_loads_a_laptop_without_graphics_help():
    # Drawn by the processor instead of the graphics chip, the shaders would run the CPU
    # hot (3 frames a second in a test browser): then the still picture is used instead,
    # and a laptop that falls behind first draws smaller, then stops.
    page = (resources.files("bau.ui") / "jarvis.html").read_text()
    assert "failIfMajorPerformanceCaveat: true" in page
    assert "llvmpipe" in page and "swiftshader" in page.lower()
    assert "LIQUID_MIN_FPS" in page and "giveUp(" in page


def test_the_anime_scenes_are_painted_live_in_jarvis():
    page = (resources.files("bau.ui") / "jarvis.html").read_text()
    assert "SCENE_FS" in page and "LOOK.live" in page           # drawn by the GPU, not a file
    assert "dusk(" in page and "summer(" in page                # the two scenes
    assert "createFramebuffer" in page and "uFullA" in page     # melted, seen through the glass
    assert "SCENE_HOLD_MS" in page                              # a scene stays longer
    assert "petals(" in page and "powerLines(" in page
    assert "woman(" in page                                     # a grown woman in each scene


def test_seven_live_scenes_in_very_different_styles():
    # Owner, 2026-10-26: "more different styles, be creative, big difference, live art".
    page = (resources.files("bau.ui") / "jarvis.html").read_text()
    order = re.search(r"SCENES = \[([^\]]*)\]", page).group(1)
    assert re.findall(r'"(\w+)"', order) == list(L.LIVE)       # the page and bau look agree
    for fn in ("neonCity(", "aurora(", "ocean(", "space(", "synthwave("):
        assert fn in page
    for i, fn in enumerate(("dusk", "summer", "neonCity", "aurora", "ocean", "space")):
        assert f"uScene < {i}.5 ? {fn}(" in page or (i == 0 and "uScene < 0.5 ? dusk(" in page)
    assert ": synthwave(P, ca, uTime);" in page


def test_render_script_reads_the_same_shader(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "render_scenes", Path(__file__).resolve().parents[1] / "scripts" / "render_scenes.py")
    rs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rs)
    assert rs.scenes() == list(L.LIVE)
    src = rs.PAGE.read_text()
    assert "void main()" in rs._js_const(src, "SCENE_FS")


def test_cli_look_flow(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    assert cli.main(["look", "flow", "gold", "earth"]) == 0
    assert json.loads(capsys.readouterr().out)["flow"] == ["gold", "earth"]
    assert cli.main(["look", "flow", "all"]) == 0                 # every picture there is
    assert len(json.loads(capsys.readouterr().out)["flow"]) == len(L.SHIPPED)
    assert cli.main(["look", "flow", "default"]) == 0
    assert json.loads(capsys.readouterr().out)["flow"] == list(L.LIVE)


# ------------------------------------------------------------------ Mission Control too

def test_mission_control_serves_the_art_and_its_choice(tmp_path):
    from bau.ui.server import _api, serve
    got = _api("/api/look", tmp_path)
    assert got["art"] == "dusk" and got["alive"] is True
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
    assert "background=/usr/share/backgrounds/bau/wall-dusk.jpg" in greeter
    assert "theme-name=Adwaita-dark" in greeter
    auto = (CONF / "includes.chroot" / "etc" / "xdg" / "autostart" /
            "bau-look.desktop").read_text()
    assert "Exec=/usr/local/bin/bau-look-desktop" in auto


def test_desktop_look_is_set_once_and_never_overrides_the_owners_choice():
    text = DESKTOP.read_text()
    assert "look-applied" in text                     # a marker: only the first login
    assert "last-image" in text and "backdrop-cycle-enable" in text
    assert "Adwaita-dark" in text


# Fake xfconf-query (properties in a file) and xrandr, as a new Xfce desktop has them:
# xfdesktop 4.20.1 (Debian 13) stores no picture setting until someone picks one.
FAKE_XFCONF = r"""#!/bin/bash
db="$FAKE_DB"; touch "$db"
chan=; prop=; val=; list=0
while (($#)); do
  case $1 in -c) chan=$2; shift ;; -p) prop=$2; shift ;; -s) val=$2; shift ;;
    -t) shift ;; -l) list=1 ;; -n|-v) ;; esac
  shift
done
if ((list)); then grep "^$chan " "$db" | cut -d' ' -f2; exit 0; fi
if [[ -n $val ]]; then grep -v "^$chan $prop " "$db" > "$db.t"; mv "$db.t" "$db"
  echo "$chan $prop $val" >> "$db"; exit 0; fi
line=$(grep "^$chan $prop " "$db") || exit 1
echo "${line#"$chan $prop "}"
"""
FAKE_XRANDR = """#!/bin/sh
echo 'Monitors: 2'
echo ' 0: +*eDP-1 1920/290x1080/170+0+0  eDP-1'
echo ' 1: +HDMI-1 1920/530x1080/300+1920+0  HDMI-1'
"""


def _run_desktop_look(tmp_path, script=DESKTOP):
    bin_ = tmp_path / "bin"
    bin_.mkdir(exist_ok=True)
    for name, body in (("xfconf-query", FAKE_XFCONF), ("xrandr", FAKE_XRANDR)):
        (bin_ / name).write_text(body)
        (bin_ / name).chmod(0o755)
    art = tmp_path / "wall-dusk.jpg"
    art.write_bytes(JPEG)
    db = tmp_path / "xfconf.db"
    if not db.exists():
        db.write_text("xfce4-desktop /last-settings-migration-version 1\n")
    env = {"PATH": f"{bin_}:/usr/bin:/bin", "HOME": str(tmp_path), "FAKE_DB": str(db),
           "BAU_LOOK_ART": str(art)}
    r = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True,
                       timeout=60)
    return r, dict(line.split(" ", 1)[1].split(" ", 1) for line in db.read_text().splitlines()
                   if line.startswith("xfce4-desktop "))


def test_a_new_xfce_desktop_gets_the_art_on_every_screen_and_workspace(tmp_path):
    # The owner saw Xfce's mouse after v2 (2026-10-26): with no picture setting stored the
    # script found nothing to change. Proved in Debian 13 with Xvfb and xfdesktop 4.20.1.
    r, props = _run_desktop_look(tmp_path)
    assert r.returncode == 0, r.stderr
    images = {k: v for k, v in props.items() if k.endswith("/last-image")}
    assert len(images) == 8                      # 2 screens x 4 workspaces (Xfce's default)
    assert "/backdrop/screen0/monitorHDMI-1/workspace3/last-image" in images
    assert set(images.values()) == {str(tmp_path / "wall-dusk.jpg")}
    assert props["/backdrop/screen0/monitoreDP-1/workspace0/backdrop-cycle-enable"] == "true"
    assert (tmp_path / ".config" / "bau" / "look-applied-v3").exists()
    # Second login: the owner's own choice stays.
    (tmp_path / "xfconf.db").write_text("")
    _, again = _run_desktop_look(tmp_path)
    assert again == {}


@pytest.mark.skipif(not shutil.which("shellcheck"), reason="needs shellcheck")
def test_shellcheck():
    r = subprocess.run(["shellcheck", str(DESKTOP)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


# ------------------------------------------------------------------ polish (overhaul check)

def test_both_pages_have_a_tab_icon_so_the_browser_logs_no_error(jarvis, tmp_path):
    # Without one the browser asks for /favicon.ico and logs a 404 on every visit.
    for name in ("jarvis.html", "page.html"):
        page = (resources.files("bau.ui") / name).read_text()
        assert '<link rel="icon" href="/icon.svg"' in page, name
    _, url = jarvis
    with urllib.request.urlopen(url + "/icon.svg") as r:
        assert r.headers["Content-Type"] == "image/svg+xml" and b"<svg" in r.read()
    from bau.ui.server import serve
    srv = serve(0, tmp_path / "mc")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/icon.svg") as r:
            assert r.headers["Content-Type"] == "image/svg+xml"
    finally:
        srv.shutdown()


def test_the_still_picture_fills_the_screen_for_a_scene_and_phones_read_the_caption():
    page = (resources.files("bau.ui") / "jarvis.html").read_text()
    assert "backgroundSize" in page and '"cover"' in page      # a scene fills, a picture fits
    phone = page[page.index("@media (max-width:760px)"):]
    assert "#caption{" in phone and "background:var(--panel)" in phone   # readable over the ring
    assert "#text::placeholder" in phone


def test_the_page_has_no_known_leaks_loops_or_echo():
    # From the overhaul review: each of these was a real path to an echo, a stuck screen,
    # a growing loop, or the art giving up for good after the laptop slept.
    page = (resources.files("bau.ui") / "jarvis.html").read_text()
    assert "micAnalyser" in page                       # the mic never plays through speakers
    assert "micSrc.disconnect()" in page and "srcNode.disconnect()" in page
    assert "catch (e) { setState(\"idle\")" in page     # a failed button never sticks on thinking
    assert "cancelAnimationFrame(eyeRaf)" in page      # one map loop, not one per click
    assert "nodesLoading" in page                      # one overview request at a time
    assert "if (now - last > 1000)" in page and "slow = 0" in page   # sleep is not slowness
    assert "gl.deleteTexture" in page                  # pictures leaving the flow are freed
    assert "wakeFail" in page                          # a wake word that can't work says so
    assert "if (wv.width !== cw)" in page              # the voice bar is not reallocated per frame
    assert "clipUrl" in page and "URL.revokeObjectURL(clipUrl)" in page
    ps = page[page.index("function paintState(s) {"):]
    assert ps.index("if (!s) return;") < ps.index("applyLook(s.look)")
