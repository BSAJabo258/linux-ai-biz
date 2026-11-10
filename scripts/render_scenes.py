"""Render stills of Jarvis's live scenes (SCENE_FS in src/bau/ui/jarvis.html) to JPEG.

The desktop, the login screen, Mission Control and computers without WebGL show these
stills; Jarvis paints the same scenes live. Uses the pre-installed Playwright Chromium
(software WebGL is fine for stills):

    python3 scripts/render_scenes.py                 # every scene, both sizes
    python3 scripts/render_scenes.py neon --out /tmp/x --time 12
"""

from __future__ import annotations

import argparse
import base64
import io
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "src" / "bau" / "ui" / "jarvis.html"
ART = ROOT / "src" / "bau" / "ui" / "art"
SIZES = {"": (1280, 720), "wall-": (1920, 1080)}

HTML = """<!doctype html><canvas id=c></canvas><script>
const GLSL_HEAD = %s;
const SCENE_FS = GLSL_HEAD + %s;
function render(w, h, scene, time) {
  const c = document.getElementById("c"); c.width = w; c.height = h;
  const gl = c.getContext("webgl", {preserveDrawingBuffer: true});
  const sh = (t, s) => {
    const o = gl.createShader(t); gl.shaderSource(o, s); gl.compileShader(o);
    if (!gl.getShaderParameter(o, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(o));
    return o;
  };
  const p = gl.createProgram();
  gl.attachShader(p, sh(gl.VERTEX_SHADER, "attribute vec2 a; varying vec2 vUv;" +
    "void main() { vUv = a * 0.5 + 0.5; vUv.y = 1.0 - vUv.y; gl_Position = vec4(a, 0.0, 1.0); }"));
  gl.attachShader(p, sh(gl.FRAGMENT_SHADER, SCENE_FS));
  gl.bindAttribLocation(p, 0, "a"); gl.linkProgram(p); gl.useProgram(p);
  const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
  const u = (n) => gl.getUniformLocation(p, n);
  gl.uniform2f(u("uRes"), w, h); gl.uniform1f(u("uTime"), time);
  gl.uniform1f(u("uScene"), scene); gl.uniform1f(u("uFlip"), 0);
  gl.viewport(0, 0, w, h); gl.drawArrays(gl.TRIANGLES, 0, 3);
  return c.toDataURL("image/png");
}
</script>"""


def _js_const(src: str, name: str) -> str:
    m = re.search(rf"const {name} = (?:GLSL_HEAD \+ )?`(.*?)`;", src, re.S)
    if not m:
        raise SystemExit(f"{name} not found in {PAGE}")
    return m.group(1)


def scenes() -> list[str]:
    m = re.search(r'SCENES = \[([^\]]*)\]', PAGE.read_text())
    return re.findall(r'"(\w+)"', m.group(1))


def render(names: list[str], out: Path, time: float, sizes: dict[str, tuple[int, int]]) -> None:
    import json

    from PIL import Image
    from playwright.sync_api import sync_playwright
    src = PAGE.read_text()
    html = HTML % (json.dumps(_js_const(src, "GLSL_HEAD")), json.dumps(_js_const(src, "SCENE_FS")))
    order = scenes()
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        exe = os.environ.get("BAU_CHROMIUM") or next(
            (p for p in ("/opt/pw-browsers/chromium",) if Path(p).exists()), None)
        browser = pw.chromium.launch(executable_path=exe, args=[
            "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page()
        page.set_content(html)
        for name in names:
            for prefix, (w, h) in sizes.items():
                url = page.evaluate("([w, h, s, t]) => render(w, h, s, t)",
                                    [w, h, order.index(name), time])
                im = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGB")
                path = out / f"{prefix}{name}.jpg"
                im.save(path, quality=88, optimize=True, progressive=True)
                print(path, im.size)
        browser.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("names", nargs="*", help="scenes (default: all)")
    ap.add_argument("--out", type=Path, default=ART)
    ap.add_argument("--time", type=float, default=20.0, help="seconds into the scene")
    ap.add_argument("--small", action="store_true", help="only the 1280x720 still")
    a = ap.parse_args()
    sizes = {"": SIZES[""]} if a.small else SIZES
    render(a.names or scenes(), a.out, a.time, sizes)


if __name__ == "__main__":
    main()
