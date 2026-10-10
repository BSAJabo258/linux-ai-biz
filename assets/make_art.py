"""Draw the README artwork (banner and feature cards, dark and light) in Jarvis's palette.

    python3 assets/make_art.py

The SVGs are self-contained (no scripts, no outside fonts or images) so GitHub shows them
as images; their animations stop when the viewer asks for reduced motion.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
FONT = "Rajdhani, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
MONO = "'JetBrains Mono', 'SFMono-Regular', Consolas, monospace"

THEMES = {
    "dark": {"bg0": "#0b4374", "bg1": "#03152c", "bg2": "#010812", "ink": "#e8f8ff",
             "dim": "#7fa8bf", "cyan": "#3fd6ff", "gold": "#ffcf4d", "line": "#3fd6ff",
             "panel": "#061624", "panel_op": "0.72", "grid_op": "0.07", "orb": "#bff3ff"},
    "light": {"bg0": "#ffffff", "bg1": "#e3eff7", "bg2": "#d5e6f1", "ink": "#08263a",
              "dim": "#3f5f72", "cyan": "#0a78a8", "gold": "#a87900", "line": "#0a78a8",
              "panel": "#ffffff", "panel_op": "0.85", "grid_op": "0.10", "orb": "#0a78a8"},
}

TAGLINE = "human-only approvals · tamper-evident audit · your laptop, USB or cloud"
CALM = """@media (prefers-reduced-motion: reduce) { * { animation: none !important; } }"""


def _sky(t: dict, w: int, h: int) -> str:
    return f"""<defs>
  <radialGradient id="sky" cx="50%" cy="45%" r="75%">
    <stop offset="0" stop-color="{t['bg0']}"/><stop offset=".55" stop-color="{t['bg1']}"/>
    <stop offset="1" stop-color="{t['bg2']}"/></radialGradient>
  <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">
    <path d="M32 0H0V32" fill="none" stroke="{t['cyan']}" stroke-width="1"
          opacity="{t['grid_op']}"/></pattern>
  <radialGradient id="glow" cx="50%" cy="50%" r="50%">
    <stop offset="0" stop-color="{t['cyan']}" stop-opacity=".55"/>
    <stop offset="1" stop-color="{t['cyan']}" stop-opacity="0"/></radialGradient>
  <linearGradient id="title" x1="0" x2="1">
    <stop offset="0" stop-color="{t['ink']}"/><stop offset=".5" stop-color="{t['cyan']}"/>
    <stop offset="1" stop-color="{t['gold']}"/></linearGradient>
</defs>
<rect width="{w}" height="{h}" rx="18" fill="url(#sky)"/>
<rect width="{w}" height="{h}" rx="18" fill="url(#grid)"/>"""


def _traces(t: dict, w: int, h: int, seed: int) -> str:
    """Circuit traces: right-angled paths with pads, a light pulse running along each."""
    rnd = random.Random(seed)
    out = []
    for i in range(14):
        left = i % 2 == 0
        y = rnd.randint(30, h - 30)
        x0 = 0 if left else w
        x1 = rnd.randint(140, 380)
        x1 = x1 if left else w - x1
        y1 = y + rnd.choice((-1, 1)) * rnd.randint(20, 70)
        x2 = x1 + (rnd.randint(40, 120) if left else -rnd.randint(40, 120))
        d = f"M{x0} {y}H{x1}L{x1 + (20 if left else -20)} {y1}H{x2}"
        dur = rnd.uniform(3.5, 7.5)
        out.append(f'<path d="{d}" class="tr"/>'
                   f'<path d="{d}" class="pulse" style="animation-duration:{dur:.1f}s;'
                   f'animation-delay:-{rnd.uniform(0, dur):.1f}s"/>'
                   f'<circle cx="{x2}" cy="{y1}" r="3" class="pad"/>')
    return "\n".join(out)


def _orb(t: dict, cx: float, cy: float, r: float) -> str:
    """A sphere of points (golden-angle spiral) inside a dashed golden halo."""
    pts = []
    n = 260
    for i in range(n):
        z = 1 - 2 * (i + 0.5) / n
        rad = math.sqrt(1 - z * z)
        a = i * math.pi * (3 - math.sqrt(5))
        x, y = rad * math.cos(a), rad * math.sin(a)
        if z < -0.15:
            continue                                     # back half hidden: reads as a ball
        size = 0.7 + 1.3 * (z + 0.15)
        pts.append(f'<circle cx="{cx + x * r:.1f}" cy="{cy + y * r:.1f}" '
                   f'r="{size:.2f}" opacity="{0.35 + 0.6 * (z + 0.15):.2f}"/>')
    return f"""<circle cx="{cx}" cy="{cy}" r="{r * 2.1:.0f}" fill="url(#glow)" class="breathe"/>
<g class="spin" style="transform-origin:{cx}px {cy}px">
  <circle cx="{cx}" cy="{cy}" r="{r * 1.32:.0f}" fill="none" stroke="{t['gold']}"
          stroke-width="2.5" stroke-dasharray="3 9" opacity=".9"/></g>
<g class="spin rev" style="transform-origin:{cx}px {cy}px">
  <circle cx="{cx}" cy="{cy}" r="{r * 1.5:.0f}" fill="none" stroke="{t['cyan']}"
          stroke-width="1" stroke-dasharray="60 14 6 14" opacity=".55"/></g>
<circle cx="{cx}" cy="{cy}" r="{r * 1.18:.0f}" fill="none" stroke="{t['gold']}"
        stroke-width="1.2" opacity=".55"/>
<g fill="{t['orb']}" class="breathe">{''.join(pts)}</g>"""


def banner(theme: str) -> str:
    t = THEMES[theme]
    w, h = 1280, 400
    return f"""<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-labelledby="t d">
<title id="t">BAU · Jarvis</title>
<desc id="d">Compliance-first AI business computer: Jarvis's orb in a golden halo.</desc>
<style>
.tr {{ fill: none; stroke: {t['line']}; stroke-width: 1.2; opacity: .28; }}
.pad {{ fill: {t['cyan']}; opacity: .6; }}
.pulse {{ fill: none; stroke: {t['cyan']}; stroke-width: 2.4; stroke-linecap: round;
         stroke-dasharray: 24 900; animation: flow linear infinite; }}
@keyframes flow {{ from {{ stroke-dashoffset: 924; }} to {{ stroke-dashoffset: 0; }} }}
.spin {{ animation: spin 28s linear infinite; }}
.rev {{ animation-direction: reverse; animation-duration: 40s; }}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
.breathe {{ animation: breathe 5s ease-in-out infinite; }}
@keyframes breathe {{ 50% {{ opacity: .72; }} }}
.cursor {{ animation: blink 1.1s steps(1) infinite; }}
@keyframes blink {{ 50% {{ opacity: 0; }} }}
{CALM}
</style>
{_sky(t, w, h)}
{_traces(t, w, h, 7)}
{_orb(t, 1080, 200, 84)}
<g font-family="{FONT}">
  <text x="72" y="92" font-family="{MONO}" font-size="15" letter-spacing="6"
        fill="{t['cyan']}">// SYSTEM ONLINE<tspan class="cursor"> _</tspan></text>
  <text x="68" y="196" font-size="96" font-weight="700" letter-spacing="8"
        fill="url(#title)">BAU · JARVIS</text>
  <text x="72" y="244" font-size="27" letter-spacing="3" fill="{t['ink']}">
    Compliance-first AI business computer</text>
  <text x="72" y="290" font-family="{MONO}" font-size="15" letter-spacing="1.5"
        fill="{t['dim']}">{TAGLINE}</text>
  <rect x="72" y="318" width="210" height="3" rx="1.5" fill="{t['gold']}"/>
  <rect x="290" y="318" width="60" height="3" rx="1.5" fill="{t['cyan']}"/>
</g>
</svg>
"""


CARDS = [
    ("JARVIS", "Voice-first assistant, live HUD.", "He stages actions; you confirm.", "orb"),
    ("COMPLIANCE", "49 regulations, 65 policies.", "PASS, REVIEW or BLOCK + evidence.",
     "shield"),
    ("APPROVALS", "Money, legal, email: SSH-signed", "by you. Never by a model.", "key"),
    ("VIDEO STUDIO", "AI clips priced before they're", "made, inside your own budget.",
     "play"),
    ("TOOLBOX + SCOUT", "77 researched open-source tools,", "inspected in quarantine first.",
     "scan"),
    ("YOUR HARDWARE", "Encrypted laptop, live USB, or", "your own cloud via SSH tunnel.",
     "node"),
]


def _icon(kind: str, x: float, y: float, t: dict) -> str:
    c, g = t["cyan"], t["gold"]
    s = f'fill="none" stroke="{c}" stroke-width="2.2" stroke-linecap="round" ' \
        'stroke-linejoin="round"'
    shapes = {
        "orb": f'<circle cx="{x}" cy="{y}" r="15" {s}/><circle cx="{x}" cy="{y}" r="22" '
               f'fill="none" stroke="{g}" stroke-width="2" stroke-dasharray="3 5"/>'
               f'<circle cx="{x}" cy="{y}" r="5" fill="{c}"/>',
        "shield": f'<path d="M{x} {y - 20}l16 6v10c0 11-7 18-16 22-9-4-16-11-16-22v-10z" {s}/>'
                  f'<path d="M{x - 7} {y}l5 5 9-10" fill="none" stroke="{g}" '
                  'stroke-width="2.4" stroke-linecap="round"/>',
        "key": f'<circle cx="{x - 8}" cy="{y}" r="9" {s}/><path d="M{x + 1} {y}h20m-6 0v7'
               f'm-6-7v5" {s}/><circle cx="{x - 8}" cy="{y}" r="3" fill="{g}"/>',
        "play": f'<rect x="{x - 20}" y="{y - 15}" width="40" height="30" rx="5" {s}/>'
                f'<path d="M{x - 5} {y - 8}l12 8-12 8z" fill="{g}"/>',
        "scan": f'<circle cx="{x - 4}" cy="{y - 4}" r="13" {s}/><path d="M{x + 6} {y + 6}'
                f'l11 11" {s}/><path d="M{x - 10} {y - 4}h12" stroke="{g}" '
                'stroke-width="2.4" stroke-linecap="round"/>',
        "node": f'<rect x="{x - 18}" y="{y - 18}" width="36" height="14" rx="3" {s}/>'
                f'<rect x="{x - 18}" y="{y + 2}" width="36" height="14" rx="3" {s}/>'
                f'<circle cx="{x + 10}" cy="{y - 11}" r="2.5" fill="{g}"/>'
                f'<circle cx="{x + 10}" cy="{y + 9}" r="2.5" fill="{g}"/>',
    }
    return shapes[kind]


def features(theme: str) -> str:
    t = THEMES[theme]
    w, h = 1280, 520
    cw, ch, gap, top = 392, 214, 24, 34
    left = (w - 3 * cw - 2 * gap) / 2
    cards = []
    for i, (title, l1, l2, icon) in enumerate(CARDS):
        x = left + (i % 3) * (cw + gap)
        y = top + (i // 3) * (ch + gap)
        cards.append(f"""<g class="card" style="animation-delay:{i * 0.35:.2f}s">
  <rect x="{x}" y="{y}" width="{cw}" height="{ch}" rx="14" fill="{t['panel']}"
        fill-opacity="{t['panel_op']}" stroke="{t['cyan']}" stroke-opacity=".35"/>
  <path d="M{x + 14} {y}h70" stroke="{t['gold']}" stroke-width="3" stroke-linecap="round"/>
  <path d="M{x + cw - 30} {y + ch}h16" stroke="{t['cyan']}" stroke-width="3"
        stroke-linecap="round"/>
  {_icon(icon, x + 52, y + 62, t)}
  <text x="{x + 94}" y="{y + 70}" font-size="21" font-weight="700" letter-spacing="2.5"
        fill="{t['ink']}">{title}</text>
  <text x="{x + 28}" y="{y + 134}" font-size="17.5" fill="{t['dim']}">{l1}</text>
  <text x="{x + 28}" y="{y + 162}" font-size="17.5" fill="{t['dim']}">{l2}</text>
</g>""")
    return f"""<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-labelledby="t d">
<title id="t">What BAU does</title>
<desc id="d">Six features: Jarvis, compliance engine, human-only approvals, video studio,
toolbox and Repo Scout, and running on hardware you own.</desc>
<style>
.card {{ animation: rise 4.5s ease-in-out infinite; }}
@keyframes rise {{ 50% {{ opacity: .86; }} }}
{CALM}
</style>
{_sky(t, w, h)}
<g font-family="{FONT}">
{chr(10).join(cards)}
</g>
</svg>
"""


def facts() -> dict[str, int]:
    """The numbers on the stats panel, read from the repository (never typed in)."""
    import sys
    sys.path.insert(0, str(HERE.parent / "src"))
    from bau.policy import PolicyEngine
    from bau.regulations import Registry
    from bau.series import Series
    from bau.toolbox import Toolbox
    reg = Registry.load()
    return {"regulations": len(reg.regs), "policies": len(PolicyEngine.load(reg).policies),
            "tools": len(Toolbox().entries), "formats": len(Series(HERE.parent).formats())}


def stats(theme: str) -> str:
    t = THEMES[theme]
    f = facts()
    tiles = [(f["regulations"], "REGULATIONS TRACKED", "each awaiting counsel review"),
             (f["policies"], "POLICY RULES", "PASS · REVIEW · BLOCK"),
             (f["tools"], "RESEARCHED TOOLS", "in the toolbox, with sources"),
             (f["formats"], "STORY FORMATS", "for the kids series engine"),
             (0, "APPROVALS BY AI", "money and legal: humans only")]
    w, h, tw = 1280, 210, 232
    gap = (w - 5 * tw) / 6
    out = []
    for i, (num, label, sub) in enumerate(tiles):
        x = gap + i * (tw + gap)
        accent = t["gold"] if i == 4 else t["cyan"]
        out.append(f"""<g class="tile" style="animation-delay:{i * .4:.1f}s">
  <rect x="{x}" y="28" width="{tw}" height="154" rx="14" fill="{t['panel']}"
        fill-opacity="{t['panel_op']}" stroke="{accent}" stroke-opacity=".4"/>
  <path d="M{x + 14} 28h54" stroke="{accent}" stroke-width="3" stroke-linecap="round"/>
  <text x="{x + tw / 2}" y="104" text-anchor="middle" font-size="58" font-weight="700"
        fill="{accent}" class="num">{num}</text>
  <text x="{x + tw / 2}" y="138" text-anchor="middle" font-size="14" font-weight="700"
        letter-spacing="1.6" fill="{t['ink']}">{label}</text>
  <text x="{x + tw / 2}" y="162" text-anchor="middle" font-size="14"
        fill="{t['dim']}">{sub}</text>
</g>""")
    return f"""<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-labelledby="t d">
<title id="t">BAU in numbers</title>
<desc id="d">{f['regulations']} regulations tracked, {f['policies']} policy rules,
{f['tools']} researched tools, {f['formats']} story formats, 0 approvals by AI.</desc>
<style>
.tile {{ animation: glow 4s ease-in-out infinite; }}
@keyframes glow {{ 50% {{ opacity: .82; }} }}
{CALM}
</style>
{_sky(t, w, h)}
<g font-family="{FONT}">
{chr(10).join(out)}
</g>
</svg>
"""


# A terminal session: real BAU commands with their output, abbreviated.
SESSION = [
    ("$", 'bau toolbox ask "stop the model making things up"'),
    (" ", "DeepEval      evals            Apache-2.0   claimed"),
    (" ", "Context7      docs-grounding   MIT          claimed"),
    (" ", "LlamaIndex    grounding        MIT          claimed"),
    ("$", "bau series plan kids-channel ep-001 --format problem-song-solution"),
    (" ", "1  hook    5s  Pip notices a small problem."),
    (" ", "2  try    13s  Pip tries to fix it alone..."),
    (" ", "3  help    9s  Mo comes to help Pip... (part 1 of 2)"),
    ("~", "6 clips · 60 s · every prompt carries the same character lock"),
    ("$", "bau usage"),
    (" ", "today    32,850 tokens · 9 calls · $0.00"),
    ("!", "98% of your daily token limit"),
]


def terminal(theme: str) -> str:
    t = THEMES[theme]
    w, top, lh = 1280, 92, 34
    h = top + lh * len(SESSION) + 48
    cycle = 22.0
    lines, keys = [], []
    at = 0.6
    for i, (kind, text) in enumerate(SESSION):
        y = top + i * lh
        start = at / cycle * 100
        type_dur = (min(2.4, 0.045 * len(text)) if kind == "$" else 0.12) / cycle * 100
        keys.append(f"@keyframes l{i} {{ 0%, {start:.2f}% {{ clip-path: inset(0 100% 0 0); }}"
                    f" {start + type_dur:.2f}%, 96% {{ clip-path: inset(0 0 0 0); }}"
                    f" 100% {{ clip-path: inset(0 100% 0 0); }} }}")
        colour = {"$": t["ink"], "~": t["gold"], "!": t["gold"]}.get(kind, t["dim"])
        prompt = ""
        if kind == "$":
            prompt = f'<tspan fill="{t["cyan"]}">jarvis@cloud</tspan><tspan fill="{t["dim"]}">' \
                     f':~$ </tspan>'
        mark = {"!": "⚠ ", "~": "✓ "}.get(kind, "")
        lines.append(f'<text x="48" y="{y}" class="ln" style="animation-name:l{i}" '
                     f'fill="{colour}">{prompt}{mark}{text}</text>')
        at += (min(2.4, 0.045 * len(text)) + 0.7) if kind == "$" else 0.35
    return f"""<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-labelledby="t d">
<title id="t">BAU at the terminal</title>
<desc id="d">Three commands: asking the toolbox, planning a kids episode, checking usage.</desc>
<style>
.ln {{ animation-duration: {cycle}s; animation-iteration-count: infinite;
       animation-timing-function: linear; clip-path: inset(0 100% 0 0); white-space: pre; }}
{chr(10).join(keys)}
@media (prefers-reduced-motion: reduce) {{ .ln {{ animation: none !important;
       clip-path: none !important; }} }}
</style>
{_sky(t, w, h)}
<rect x="24" y="22" width="{w - 48}" height="{h - 44}" rx="14" fill="{t['panel']}"
      fill-opacity="{t['panel_op']}" stroke="{t['cyan']}" stroke-opacity=".35"/>
<circle cx="52" cy="48" r="6" fill="#ff5f57"/><circle cx="74" cy="48" r="6" fill="#febc2e"/>
<circle cx="96" cy="48" r="6" fill="#28c840"/>
<text x="{w / 2}" y="53" text-anchor="middle" font-family="{MONO}" font-size="14"
      fill="{t['dim']}">bau — outputs abbreviated, sample data</text>
<g font-family="{MONO}" font-size="19" xml:space="preserve">
{chr(10).join(lines)}
</g>
</svg>
"""


def main() -> None:
    for theme in THEMES:
        (HERE / f"banner-{theme}.svg").write_text(banner(theme))
        (HERE / f"features-{theme}.svg").write_text(features(theme))
        (HERE / f"stats-{theme}.svg").write_text(stats(theme))
        (HERE / f"terminal-{theme}.svg").write_text(terminal(theme))


if __name__ == "__main__":
    main()
