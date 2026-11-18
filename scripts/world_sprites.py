"""Draw the operations world's characters as a sprite sheet (docs/visual/VISUAL_ART_DIRECTION.md).

Run:  python3 scripts/world_sprites.py
Writes src/bau/ui/world/characters.png (every character, every animation) and characters.json
(where each frame is). Each character is one of the owner's AI assistants, drawn from his
picture of 2026-11-17: glamorous adult women in glossy neon two-piece outfits with chokers,
armbands and boots, each with her own hair, skin, colours and the tool of her job.

High definition (the owner, 2026-11-17: "best graphics possible"): every frame is drawn at three
times its size on a 64 x 88 design grid, with soft shading, gloss and a detailed face, then
smoothed down to 96 x 132 and given a crisp outline and a neon rim light in her own colour.
Same input, same pixels: tests/test_world_art.py rebuilds the sheet and compares it byte for
byte.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

GW, GH = 64, 88                     # the design grid
SS = 3                              # drawn this many times bigger, then smoothed down
W, H = 96, 132                      # one frame on the sheet and on screen (scale 1)
K = W / GW                          # grid unit -> frame pixels
OUT = Path(__file__).resolve().parents[1] / "src" / "bau" / "ui" / "world"
ANIMS = (("idle", 2), ("walk_front", 4), ("walk_back", 4), ("work", 4), ("wait", 2),
         ("blocked", 2), ("done", 2))
OUTLINE = (18, 12, 26, 255)
LIPS = (190, 58, 92)
LASH = (26, 16, 22)

# The cast: the real agents (agent folders researcher and producer), Jarvis herself (her
# autopilot does real jobs), and four more looks for the agents the owner adds. All are
# fictional adult women; none is drawn from a real person.
CAST = {
    "jarvis": {"skin": (196, 136, 98), "hair": (28, 20, 24), "suit": (24, 26, 38),
               "trim": (63, 214, 255), "eye": (110, 70, 40), "hairdo": "long", "len": 66,
               "glasses": False,
               "role": "the lead: long black hair, black and cyan glossy two-piece, glowing "
                       "choker, a tablet she plans on"},
    "researcher": {"skin": (178, 118, 84), "hair": (36, 24, 26), "suit": (40, 70, 200),
                   "trim": (120, 200, 255), "eye": (80, 54, 36), "hairdo": "bun", "len": 0,
                   "glasses": True,
                   "role": "dark hair up in a bun, glasses, royal-blue two-piece, reads a book"},
    "producer": {"skin": (240, 196, 170), "hair": (196, 44, 38), "suit": (176, 22, 38),
                 "trim": (255, 110, 120), "eye": (60, 120, 70), "hairdo": "long", "len": 60,
                 "glasses": False,
                 "role": "long red hair, red glossy two-piece, films with a camera"},
    "engineer": {"skin": (228, 182, 150), "hair": (246, 222, 150), "suit": (34, 30, 30),
                 "trim": (255, 200, 70), "eye": (60, 110, 160), "hairdo": "long", "len": 56,
                 "glasses": True,
                 "role": "long blonde hair, glasses, black and gold two-piece, a gold wrench"},
    # More looks from the same picture, for agents without one of their own (world.py)
    "coordinator": {"skin": (214, 160, 120), "hair": (22, 18, 28), "suit": (120, 50, 190),
                    "trim": (200, 140, 255), "eye": (80, 54, 40), "hairdo": "long", "len": 64,
                    "glasses": False,
                    "role": "long black hair, violet glossy two-piece and boots, a tablet"},
    "analyst": {"skin": (120, 74, 50), "hair": (30, 20, 18), "suit": (200, 150, 40),
                "trim": (255, 236, 150), "eye": (60, 40, 30), "hairdo": "curls", "len": 44,
                "glasses": False,
                "role": "big dark curls, gold glossy two-piece, a tablet"},
    "architect": {"skin": (236, 200, 176), "hair": (236, 236, 246), "suit": (214, 222, 238),
                  "trim": (120, 220, 255), "eye": (80, 130, 180), "hairdo": "long", "len": 60,
                  "glasses": False,
                  "role": "long platinum hair, white glossy two-piece, a tablet"},
}


def _shade(c: tuple[int, ...], k: float) -> tuple[int, int, int, int]:
    return tuple(max(0, min(255, round(v * k))) for v in c[:3]) + (255,)


def _mix(a: tuple[int, ...], b: tuple[int, ...], t: float) -> tuple[int, int, int, int]:
    return tuple(round(a[i] * (1 - t) + b[i] * t) for i in range(3)) + (255,)


class Frame:
    """One frame: drawn big on the design grid, finished small and crisp."""

    def __init__(self, rim: tuple[int, ...]) -> None:
        self.big = Image.new("RGBA", (GW * SS, GH * SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.big)
        self.rim = rim
        self.fx: list[tuple[float, float, tuple[int, ...]]] = []   # effects: after the outline

    @staticmethod
    def _p(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [(x * SS, y * SS) for x, y in pts]

    def poly(self, pts: list[tuple[float, float]], c: tuple[int, ...]) -> None:
        self.d.polygon(self._p(pts), fill=_shade(c, 1.0))

    def oval(self, x0: float, y0: float, x1: float, y1: float, c: tuple[int, ...]) -> None:
        self.d.ellipse([x0 * SS, y0 * SS, x1 * SS - 1, y1 * SS - 1], fill=_shade(c, 1.0))

    def box(self, x0: float, y0: float, x1: float, y1: float, c: tuple[int, ...]) -> None:
        self.d.rectangle([x0 * SS, y0 * SS, x1 * SS - 1, y1 * SS - 1], fill=_shade(c, 1.0))

    def line(self, pts: list[tuple[float, float]], c: tuple[int, ...], w: float = 1) -> None:
        self.d.line(self._p(pts), fill=_shade(c, 1.0), width=max(1, round(w * SS)))

    def lit_oval(self, x0: float, y0: float, x1: float, y1: float, c: tuple[int, ...]) -> None:
        """Lit from the top left: a shade on the right, a soft highlight top left."""
        self.oval(x0, y0, x1, y1, _shade(c, 0.78))
        self.oval(x0, y0, x1 - (x1 - x0) * 0.18, y1 - (y1 - y0) * 0.06, c)
        w, h = x1 - x0, y1 - y0
        self.oval(x0 + w * 0.18, y0 + h * 0.12, x0 + w * 0.5, y0 + h * 0.42, _shade(c, 1.1))

    def lit_poly(self, pts: list[tuple[float, float]], c: tuple[int, ...]) -> None:
        cx = sum(x for x, _ in pts) / len(pts)
        self.poly(pts, _shade(c, 0.8))
        self.poly([(x - 1.2 if x > cx else x, y) for x, y in pts], c)

    def gloss_oval(self, x0: float, y0: float, x1: float, y1: float, c: tuple[int, ...]) -> None:
        """Glossy outfit: deep colour, a dark lower edge and a bright shine."""
        self.oval(x0, y0, x1, y1, _shade(c, 0.62))
        self.oval(x0, y0, x1, y1 - (y1 - y0) * 0.16, c)
        w, h = x1 - x0, y1 - y0
        shine = _shade(c, 2.4) if max(c[:3]) < 60 else _mix(c, (255, 255, 255), 0.6)
        self.oval(x0 + w * 0.22, y0 + h * 0.16, x0 + w * 0.46, y0 + h * 0.4, shine)

    def gloss_poly(self, pts: list[tuple[float, float]], c: tuple[int, ...],
                   streak: tuple[tuple[float, float], tuple[float, float]] | None = None) -> None:
        self.poly(pts, c)
        if streak:
            shine = _shade(c, 2.4) if max(c[:3]) < 60 else _mix(c, (255, 255, 255), 0.55)
            self.line(list(streak), shine, 0.8)

    def glow(self, x: float, y: float, c: tuple[int, ...]) -> None:
        self.fx.append((x, y, c))

    def finish(self) -> Image.Image:
        im = self.big.resize((W, H), Image.Resampling.LANCZOS)
        px = im.load()
        for i in range(W):                                  # a crisp silhouette
            for j in range(H):
                r, g, b, a = px[i, j]
                px[i, j] = (r, g, b, 255) if a >= 110 else (0, 0, 0, 0)
        src = im.copy()
        s = src.load()
        solid = [[s[i, j][3] > 0 for j in range(H)] for i in range(W)]
        for i in range(W):
            for j in range(H):
                if solid[i][j]:
                    if (i > 0 and not solid[i - 1][j]) or (j > 0 and not solid[i][j - 1]):
                        px[i, j] = _mix(s[i, j], self.rim, 0.38)      # neon rim light
                    continue
                if any(0 <= i + a < W and 0 <= j + b < H and solid[i + a][j + b]
                       for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    px[i, j] = OUTLINE
        for x, y, c in self.fx:                            # sparks, "!" and the check: 2x2
            for a in range(2):
                for b in range(2):
                    xi, yj = round(x * K) + a, round(y * K) + b
                    if 0 <= xi < W and 0 <= yj < H:
                        px[xi, yj] = _shade(c, 1.0)
        return im


def hair_back(f: Frame, p: dict, back: bool, y0: float) -> None:
    hair = p["hair"]
    if p["hairdo"] == "long":
        end = p["len"] + (4 if back else 0)
        f.poly([(21, 14 + y0), (43, 14 + y0), (45, end + y0), (32, end + 3 + y0),
                (19, end + y0)], _shade(hair, 0.85))
        for x in (24, 28, 32, 36, 40):                     # strands
            f.line([(x, 20 + y0), (x + (1 if x > 32 else -1), end - 2 + y0)],
                   _shade(hair, 0.65), 0.5)
    elif p["hairdo"] == "curls":
        for cx, cy in ((19, 16), (45, 16), (17, 26), (47, 26), (19, 36), (45, 36), (22, 44),
                       (42, 44), (32, 40)):
            f.oval(cx - 6, cy - 6 + y0, cx + 6, cy + 6 + y0, _shade(hair, 0.85))
            f.oval(cx - 3, cy - 4 + y0, cx + 1, cy + y0, _shade(hair, 1.6))


def hair_front(f: Frame, p: dict, back: bool, y0: float) -> None:
    hair, do = p["hair"], p["hairdo"]
    if do == "curls":
        for cx, cy in ((22, 9), (28, 5), (35, 5), (41, 9), (20, 16), (44, 16)):
            f.oval(cx - 5, cy - 5 + y0, cx + 5, cy + 5 + y0, hair)
            f.oval(cx - 3, cy - 3 + y0, cx, cy + y0, _shade(hair, 1.7))
        return
    f.oval(22.5, 4 + y0, 41.5, 17 + y0, hair)              # crown
    f.oval(25, 5 + y0, 33, 9 + y0, _mix(hair, (255, 255, 255), 0.35))    # shine
    if back:
        f.oval(22, 8 + y0, 42, 30 + y0, hair)
        if do == "bun":
            f.oval(26, -1 + y0, 38, 10 + y0, hair)
        return
    if do == "bun":
        f.oval(26, -1 + y0, 38, 10 + y0, hair)
        f.oval(28, 0 + y0, 33, 4 + y0, _mix(hair, (255, 255, 255), 0.35))
        f.poly([(23, 12 + y0), (26, 12 + y0), (25, 22 + y0), (23, 20 + y0)], hair)
        f.poly([(41, 12 + y0), (38, 12 + y0), (39, 22 + y0), (41, 20 + y0)], hair)
    else:
        f.poly([(22, 12 + y0), (25.5, 12 + y0), (24.6, 34 + y0), (21, 36 + y0)], hair)  # sides
        f.poly([(42, 12 + y0), (38.5, 12 + y0), (39.4, 34 + y0), (43, 36 + y0)], hair)
        f.poly([(24.5, 11 + y0), (37, 11 + y0), (31, 15 + y0), (25.5, 14.5 + y0)], hair)  # fringe
        f.line([(26.5, 12 + y0), (29.5, 13.8 + y0)], _mix(hair, (255, 255, 255), 0.3), 0.5)


def face(f: Frame, p: dict, y0: float, kind: str) -> None:
    sk = p["skin"]
    f.oval(27, 22 + y0, 30, 25 + y0, _mix(sk, (240, 120, 130), 0.25))  # blush
    f.oval(34, 22 + y0, 37, 25 + y0, _mix(sk, (240, 120, 130), 0.25))
    f.line([(32.5, 21 + y0), (32, 23.5 + y0)], _shade(sk, 0.78), 0.5)  # nose
    f.line([(26.5, 15.5 + y0), (30, 15 + y0)], _shade(p["hair"], 0.9), 0.6)   # brows
    f.line([(34, 15 + y0), (37.5, 15.5 + y0)], _shade(p["hair"], 0.9), 0.6)
    if kind == "closed":
        for x0 in (27, 34):
            f.line([(x0, 19 + y0), (x0 + 1.5, 20 + y0), (x0 + 3, 19 + y0)], LASH, 0.6)
    elif kind == "x":
        for x0 in (27, 34):
            f.line([(x0, 17 + y0), (x0 + 3, 20 + y0)], (255, 77, 94), 0.7)
            f.line([(x0 + 3, 17 + y0), (x0, 20 + y0)], (255, 77, 94), 0.7)
    else:
        for x0, wing in ((27, -1), (34, 1)):
            f.oval(x0, 17.5 + y0, x0 + 3.2, 20.5 + y0, (250, 248, 246))
            f.oval(x0 + 0.8, 17.6 + y0, x0 + 2.6, 20.4 + y0, p["eye"])
            f.oval(x0 + 1.3, 18.3 + y0, x0 + 2.1, 19.6 + y0, LASH)
            f.oval(x0 + 1.0, 18.0 + y0, x0 + 1.6, 18.6 + y0, (255, 255, 255))
            edge = x0 + (3.2 if wing > 0 else 0)
            f.line([(x0, 17.4 + y0), (x0 + 3.2, 17.4 + y0), (edge + wing, 16.6 + y0)], LASH, 0.6)
    f.oval(30.6, 25.4 + y0, 34.4, 26.8 + y0, _shade(LIPS, 0.85))       # lips
    f.oval(31, 26.2 + y0, 34, 27.8 + y0, LIPS)
    f.oval(31.8, 26.5 + y0, 32.8, 27.1 + y0, _mix(LIPS, (255, 255, 255), 0.5))


def glasses(f: Frame, y0: float) -> None:
    for x0 in (26, 33.5):
        f.d.ellipse([x0 * SS, 16.4 * SS + y0 * SS, (x0 + 4.6) * SS, 21.4 * SS + y0 * SS],
                    outline=_shade((50, 34, 34), 1.0), width=SS // 2 + 1)
    f.line([(30.6, 18.4 + y0), (33.5, 18.4 + y0)], (50, 34, 34), 0.4)


def arm(f: Frame, p: dict, side: int, a: int, y0: float) -> None:
    """``side`` -1 left, 1 right; ``a`` raises it that many grid pixels (6 and up: overhead)."""
    sk, suit, trim = p["skin"], p["suit"], p["trim"]
    sx = 32 + side * 10.5
    if a >= 6:
        x = 32 + side * 14
        f.lit_poly([(x - 2, 36 + y0), (x + 2, 36 + y0), (x + 1.6, 6 + y0), (x - 1.6, 6 + y0)], sk)
        f.oval(x - 2.2, 2 + y0, x + 2.2, 7.5 + y0, sk)                   # hand
        f.box(x - 2, 14 + y0, x + 2, 16 + y0, suit)
        f.box(x - 2, 14.6 + y0, x + 2, 15.2 + y0, trim)
        return
    lift = a * 2
    top, hand = 35 + y0, 61 + y0 - lift
    ox = sx + side * 1.5
    f.lit_poly([(sx - 2.2, top), (sx + 2.2, top), (ox + 1.6, hand), (ox - 1.6, hand)], sk)
    f.oval(ox - 2, hand - 1, ox + 2, hand + 3.5, sk)
    f.box(sx - 2.3, 41 + y0 - lift * 0.3, sx + 2.3, 43.4 + y0 - lift * 0.3, suit)   # armband
    f.box(sx - 2.3, 41.8 + y0 - lift * 0.3, sx + 2.3, 42.4 + y0 - lift * 0.3, trim)


def body(f: Frame, p: dict, who: str, back: bool, leg: int = 0, arm_l: int = 0,
         arm_r: int = 0, bob: int = 0) -> None:
    """The woman: hair behind, legs in glossy boots, hips, waist, the two-piece, arms, neck,
    choker, head and hair. ``leg`` swings the legs (-1, 0, 1), ``arm_*`` raise the arms,
    ``bob`` moves the upper body down."""
    y0 = bob * 1.0
    sk, suit, trim = p["skin"], p["suit"], p["trim"]
    hair_back(f, p, back, y0)
    for side in (-1, 1):                                            # legs
        up = max(0, leg if side < 0 else -leg) * 4
        cx = 32 + side * 4.5
        f.lit_poly([(cx - 4.5, 57), (cx + 4.5, 57), (cx + 3, 70 - up), (cx - 3, 70 - up)], sk)
        f.gloss_poly([(cx - 3.4, 66 - up), (cx + 3.4, 66 - up), (cx + 2.6, 83 - up),
                      (cx - 2.6, 83 - up)], suit,
                     ((cx - 1.6, 68 - up), (cx - 1.2, 80 - up)))
        f.box(cx - 3.4, 66 - up, cx + 3.4, 67.4 - up, trim)        # boot top glow
        f.poly([(cx - 2.6, 82 - up), (cx + 2.6, 82 - up), (cx + 2, 87 - up),
                (cx - 2.4, 87 - up)], _shade(suit, 0.55))           # heel
    f.lit_oval(21, 48 + y0, 43, 61 + y0, sk)                        # hips
    f.lit_poly([(25, 40 + y0), (39, 40 + y0), (37.5, 52 + y0), (26.5, 52 + y0)], sk)  # waist
    f.oval(31.4, 46 + y0, 32.8, 47.6 + y0, _shade(sk, 0.75))        # navel
    f.lit_poly([(21, 33 + y0), (43, 33 + y0), (41.5, 43 + y0), (22.5, 43 + y0)], sk)  # chest
    f.gloss_poly([(22, 50.5 + y0), (42, 50.5 + y0), (38, 58 + y0), (32, 60 + y0),
                  (26, 58 + y0)], suit, ((25, 52 + y0), (29, 52 + y0)))           # bottom
    f.box(22, 50.4 + y0, 42, 51.4 + y0, trim)                       # waistband glow
    if back:
        f.box(21.5, 39 + y0, 42.5, 41 + y0, suit)                   # the top's strap
        f.box(21.5, 39.5 + y0, 42.5, 40.2 + y0, trim)
    else:
        f.line([(26, 36.5 + y0), (30, 31 + y0)], suit, 0.6)        # straps
        f.line([(38, 36.5 + y0), (34, 31 + y0)], suit, 0.6)
        f.gloss_oval(22, 35.5 + y0, 32.6, 44.5 + y0, suit)          # the top
        f.gloss_oval(31.4, 35.5 + y0, 42, 44.5 + y0, suit)
        f.oval(30.6, 38.4 + y0, 33.4, 41.2 + y0, trim)              # its ring
        f.oval(31.4, 39.2 + y0, 32.6, 40.4 + y0, suit)
    for side, a in ((-1, arm_l), (1, arm_r)):
        if a < 6:
            arm(f, p, side, a, y0)
    f.lit_poly([(29, 26 + y0), (35, 26 + y0), (35.5, 34 + y0), (28.5, 34 + y0)], sk)   # neck
    f.box(28.4, 30 + y0, 35.6, 32.4 + y0, trim)                     # choker
    f.box(28.4, 30.6 + y0, 35.6, 31.6 + y0, _shade(trim, 0.6))
    f.oval(31, 31.2 + y0, 33, 33.8 + y0, trim)                      # its pendant
    f.lit_oval(24.5, 9 + y0, 39.5, 29 + y0, sk)                     # face
    hair_front(f, p, back, y0)
    if who == "jarvis" and not back:
        f.glow(32, 39.5 + y0, (190, 245, 255))                      # her mark
    for side, a in ((-1, arm_l), (1, arm_r)):
        if a >= 6:
            arm(f, p, side, a, y0)


def tool(f: Frame, who: str, p: dict, k: int, y0: float) -> None:
    """What each assistant works with; ``k`` is the frame (0-3)."""
    if who == "jarvis" or who not in ("researcher", "producer", "engineer"):
        scr = p["trim"] if who != "jarvis" else (63, 214, 255)      # a holographic tablet
        f.poly([(17, 44 + y0), (47, 44 + y0), (46, 58 + y0), (18, 58 + y0)], (16, 20, 34))
        f.box(19, 46 + y0, 45, 56 + y0, _shade(scr, 0.85 if k % 2 else 1.0))
        f.box(19, 46 + y0, 45, 47 + y0, _mix(scr, (255, 255, 255), 0.6))
        for i in range(k + 1):
            f.box(21 + i * 6, 54 + y0 - i * 2, 24 + i * 6, 55 + y0, (255, 255, 255))
        f.line([(21, 49 + y0), (40, 49 + y0)], _shade(scr, 0.6), 0.5)
    elif who == "researcher":                                       # an open book
        f.poly([(16, 45 + y0), (48, 45 + y0), (47, 57 + y0), (17, 57 + y0)], (60, 40, 96))
        f.box(18, 45 + y0, 31.6, 55 + y0, (252, 248, 234))
        f.box(32.4, 45 + y0, 46, 55 + y0, (252, 248, 234))
        for r in range(4):
            f.line([(20, 47.5 + y0 + r * 2), (29.5, 47.5 + y0 + r * 2)], (150, 150, 172), 0.4)
            f.line([(34.5, 47.5 + y0 + r * 2), (44, 47.5 + y0 + r * 2)], (150, 150, 172), 0.4)
        x = 28 + k * 2.5                                            # the page turning
        f.poly([(32, 45 + y0), (x, 43 + y0), (x, 54 + y0), (32, 55 + y0)], (232, 226, 210))
    elif who == "producer":                                         # a camera at her eye
        f.poly([(35, 13 + y0), (54, 13 + y0), (54, 26 + y0), (35, 26 + y0)], (34, 34, 44))
        f.box(37, 11 + y0, 43, 13 + y0, (34, 34, 44))
        f.oval(41, 15 + y0, 51, 25 + y0, (20, 20, 26))
        f.oval(42.5, 16.5 + y0, 49.5, 23.5 + y0, (90, 160, 220))
        f.oval(43.5, 17.2 + y0, 46, 19.6 + y0, (220, 240, 255))
        f.box(51.5, 14 + y0, 53.5, 16 + y0, (255, 77, 94))          # recording light
        if k == 2:
            for x, y in ((56, 9), (58, 6), (54, 6), (59, 11)):
                f.glow(x, y + y0, (255, 255, 210))
    else:                                                           # a gold wrench, swung
        y = (24, 30, 36, 30)[k] + y0
        f.poly([(44.5, y), (47.5, y), (47.5, y + 16), (44.5, y + 16)], p["trim"])
        f.poly([(42, y - 5), (50, y - 5), (49, y + 1), (43, y + 1)], p["trim"])
        f.box(44.5, y - 4, 47.5, y - 1, (40, 30, 20))
        f.line([(45.4, y + 1), (45.4, y + 15)], (255, 246, 210), 0.5)
        if k == 2:
            for x, yy in ((52, y + 12), (54, y + 9), (51, y + 7)):
                f.glow(x, yy, (255, 236, 150))


def frames(who: str) -> dict[str, list[Image.Image]]:
    p = CAST[who]
    out: dict[str, list[Image.Image]] = {}

    def make(back: bool = False, **kw: int) -> Frame:
        f = Frame(p["trim"])
        body(f, p, who, back, **kw)
        return f

    def look(f: Frame, bob: float, kind: str = "open") -> None:
        face(f, p, bob, kind)
        if p["glasses"]:
            glasses(f, bob)

    out["idle"] = []
    for k in range(2):
        f = make(bob=k)
        look(f, k, "closed" if k else "open")
        out["idle"].append(f.finish())
    for name, back in (("walk_front", False), ("walk_back", True)):
        out[name] = []
        for k in range(4):
            leg, bob = (1, 0, -1, 0)[k], (0, 1, 0, 1)[k]
            f = make(back=back, leg=leg, bob=bob, arm_l=(2, 0, -1, 0)[k] + 1,
                     arm_r=(-1, 0, 2, 0)[k] + 1)
            if not back:
                look(f, bob)
            out[name].append(f.finish())
    out["work"] = []
    for k in range(4):
        bob = k % 2
        f = make(bob=bob, arm_l=3, arm_r=3 if who != "engineer" else (6, 3, 0, 3)[k])
        look(f, bob)
        tool(f, who, p, k, bob)
        out["work"].append(f.finish())
    out["wait"] = []
    for k in range(2):
        f = make(arm_r=10)
        look(f, 0)
        for j in range(5):                                          # "!" above the hand
            f.glow(54, 0.5 + j * 1.3 + k, (255, 179, 64))
        f.glow(54, 9 + k, (255, 179, 64))
        out["wait"].append(f.finish())
    out["blocked"] = []
    for k in range(2):
        f = make(bob=2, arm_l=-1, arm_r=-1)
        look(f, 2, "x")
        for x, y in (((10, 12), (54, 18), (48, 8)), ((52, 10), (12, 20), (18, 6)))[k]:
            f.glow(x, y, (255, 222, 60))
            f.glow(x + 1.4, y + 1.4, (255, 77, 94))
        out["blocked"].append(f.finish())
    out["done"] = []
    for k in range(2):
        f = make(arm_l=10, arm_r=10, bob=-k)
        look(f, -k, "closed")
        for x, y in ((24, 6), (26, 8), (28, 10), (30, 8), (32, 6), (34, 4), (36, 2), (38, 0)):
            f.glow(x + 18, y + 2 - k, (70, 242, 164))               # a check mark by her hand
        out["done"].append(f.finish())
    return out


def build() -> tuple[Image.Image, dict]:
    cols = max(n for _, n in ANIMS)
    sheet = Image.new("RGBA", (W * cols, H * len(ANIMS) * len(CAST)), (0, 0, 0, 0))
    meta: dict = {"frame": [W, H], "scale": 1, "anchor": [W // 2, H - 1], "characters": {}}
    for ci, who in enumerate(CAST):
        fr = frames(who)
        meta["characters"][who] = {"role": CAST[who]["role"], "animations": {}}
        for ai, (anim, n) in enumerate(ANIMS):
            row = ci * len(ANIMS) + ai
            for k in range(n):
                sheet.paste(fr[anim][k], (k * W, row * H))
            meta["characters"][who]["animations"][anim] = {"row": row, "frames": n}
    return sheet, meta


def main() -> None:
    sheet, meta = build()
    OUT.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT / "characters.png", optimize=True)
    (OUT / "characters.json").write_text(json.dumps(meta, indent=1, sort_keys=True) + "\n")
    print(f"wrote {OUT / 'characters.png'} {sheet.size} and characters.json")


if __name__ == "__main__":
    main()
