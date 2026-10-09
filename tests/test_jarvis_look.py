"""The Jarvis look: a living orb, energy streams, circuit traces, a voice bar. Written
before the code. The page must stay accessible and calm for reduced-motion users."""

import re
from importlib import resources

from bau.accessibility import lint_html

PAGE = (resources.files("bau.ui") / "jarvis.html").read_text()


def test_orb_is_a_rotating_particle_sphere_in_a_golden_halo():
    assert "function drawOrb" in PAGE
    n = re.search(r"const ORB_POINTS = (\d+)", PAGE)
    assert n and int(n.group(1)) >= 400
    assert "--gold" in PAGE and "function drawHalo" in PAGE


def test_energy_streams_and_circuit_traces_run_to_every_node():
    assert "function drawStreams" in PAGE and "function drawTraces" in PAGE
    assert re.search(r"for \(const n of NODES\)[^}]*trace", PAGE, re.S)


def test_voice_bar_speaking_pill_and_chat_voice_toggle():
    assert 'id="wave"' in PAGE and "function drawWave" in PAGE
    pill = re.search(r'<button[^>]*id="speakpill"[^>]*>', PAGE)
    assert pill and 'data-key="S"' in pill.group(0)
    mode = re.search(r'<button[^>]*id="modepill"[^>]*>', PAGE)
    assert mode and 'data-key="V"' in mode.group(0)
    help_box = PAGE[PAGE.index('id="help"'):]
    assert "<kbd>S</kbd>" in help_box and "<kbd>V</kbd>" in help_box


def test_motion_is_calm_for_reduced_motion_and_the_page_stays_accessible():
    assert 'matchMedia("(prefers-reduced-motion: reduce)")' in PAGE
    assert "REDUCED" in PAGE.split("function drawStreams")[1][:1500]
    assert lint_html(PAGE) == []


def test_the_page_script_parses(tmp_path):
    """A text check can't see a broken script; Node's parser can (CI runners have Node)."""
    import shutil
    import subprocess

    import pytest
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js not installed here; CI runs this check")
    js = tmp_path / "page.js"
    js.write_text(PAGE.split("<script>")[1].split("</script>")[0])
    r = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
