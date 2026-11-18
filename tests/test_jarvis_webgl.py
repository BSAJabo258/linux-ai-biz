"""Jarvis's WebGL renderer check: no deprecated extension where RENDERER already names the chip.

Firefox printed "WEBGL_debug_renderer_info is deprecated ... Please use RENDERER." from
jarvis.html (the owner's desktop, 2026-11-18). Firefox's gl.RENDERER is the real renderer;
Chrome's says "WebKit WebGL" and still needs the extension. Both canvases use rendererName.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PAGE = (Path(__file__).resolve().parents[1] / "src/bau/ui/jarvis.html").read_text()
SCRIPT = PAGE.split("<script>")[1].split("</script>")[0]


def helper() -> str:
    m = re.search(r"^function rendererName\(gl\) \{.*?^\}", SCRIPT, re.S | re.M)
    assert m, "rendererName(gl) is defined once in the page script"
    return m.group(0)


def test_one_helper_and_both_canvases_use_it():
    assert SCRIPT.count("function rendererName(gl)") == 1
    # the extension is named only inside the helper
    assert SCRIPT.count("WEBGL_debug_renderer_info") == 1
    assert "WEBGL_debug_renderer_info" in helper()
    assert "/llvmpipe|swiftshader|software|softpipe/i.test(rendererName(gl))" in SCRIPT
    assert "SOFTWARE_GL.test(rendererName(gl))" in SCRIPT


CASES = """
const RENDERER = 0x1F01, UNMASKED = 0x9246;
function fake(renderer, unmasked, opts = {}) {
  const asked = [];
  return { RENDERER, asked,
    getParameter(p) { if (opts.throws) throw new Error("lost");
      return p === RENDERER ? renderer : p === UNMASKED ? unmasked : null; },
    getExtension(n) { asked.push(n); return unmasked === undefined ? null
      : { UNMASKED_RENDERER_WEBGL: UNMASKED }; } };
}
const out = {};
let g = fake("llvmpipe (LLVM 19, 256 bits)", "unused");          // Firefox: RENDERER is real
out.firefox = [rendererName(g), g.asked];
g = fake("WebKit WebGL", "ANGLE (Google, Vulkan (SwiftShader Device))");   // Chrome
out.chrome = [rendererName(g), g.asked];
g = fake("WebKit WebGL", undefined);                            // Chrome without the extension
out.chrome_noext = [rendererName(g), g.asked];
g = fake("", "Mesa Intel(R) UHD");                              // empty: ask the extension
out.empty = [rendererName(g), g.asked];
g = fake(null, null, { throws: true });                         // a lost context
out.throws = [rendererName(g), g.asked];
console.log(JSON.stringify(out));
"""


def test_renderer_name_on_fake_contexts(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js not installed here; CI runs this check")
    js = tmp_path / "r.js"
    js.write_text(helper() + "\n" + CASES)
    r = subprocess.run([node, str(js)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["firefox"] == ["llvmpipe (LLVM 19, 256 bits)", []]       # never asks Firefox
    assert out["chrome"] == ["ANGLE (Google, Vulkan (SwiftShader Device))",
                             ["WEBGL_debug_renderer_info"]]
    assert out["chrome_noext"] == ["WebKit WebGL", ["WEBGL_debug_renderer_info"]]
    assert out["empty"] == ["Mesa Intel(R) UHD", ["WEBGL_debug_renderer_info"]]
    assert out["throws"] == ["", []]
