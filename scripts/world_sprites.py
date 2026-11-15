"""Draw the operations world's characters as pixel-art sprite sheets
(docs/visual/VISUAL_ART_DIRECTION.md).

Run:  python3 scripts/world_sprites.py
Writes src/bau/ui/world/characters.png (every character, every animation) and characters.json
(where each frame is). Each character is designed from parts: a robot body in the style of the
owner's reference pictures, then its role's own colours, clothes and tools. Same input, same
pixels: tests/test_world_art.py rebuilds the sheet and compares it byte for byte.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

W, H = 32, 44                       # one frame, in art pixels (drawn 3x on screen)
OUT = Path(__file__).resolve().parents[1] / "src" / "bau" / "ui" / "world"
ANIMS = (("idle", 2), ("walk_front", 4), ("walk_back", 4), ("work", 4), ("wait", 2),
         ("blocked", 2), ("done", 2))
OUTLINE = (16, 24, 36, 255)

# The cast: the real agents (agent folders researcher and producer), Jarvis himself (his
# autopilot does real jobs), and an engineer for any agent the owner adds later.
CAST = {
    "jarvis": {"head": (238, 232, 214), "body": (112, 86, 214), "trim": (255, 207, 77),
               "eye": (63, 214, 255), "visor": (12, 18, 40), "limb": (150, 132, 210),
               "role": "the executive: violet cape, gold halo, a tablet he plans on"},
    "researcher": {"head": (226, 236, 242), "body": (244, 248, 250), "trim": (40, 170, 190),
                   "eye": (70, 242, 164), "visor": (10, 26, 36), "limb": (150, 172, 186),
                   "role": "a lab coat, round glasses, a bulb on its antenna, reads a book"},
    "producer": {"head": (232, 226, 240), "body": (170, 60, 150), "trim": (255, 120, 200),
                 "eye": (255, 179, 64), "visor": (30, 10, 30), "limb": (160, 140, 170),
                 "role": "a beret and headphones, a magenta jacket, films with a camera"},
    "engineer": {"head": (220, 228, 234), "body": (70, 90, 110), "trim": (255, 140, 40),
                 "eye": (63, 214, 255), "visor": (10, 20, 30), "limb": (130, 146, 160),
                 "role": "an orange hard hat, a hi-vis vest, a tool belt and a wrench"},
}


def _shade(c: tuple[int, ...], k: float) -> tuple[int, int, int, int]:
    return tuple(max(0, min(255, round(v * k))) for v in c[:3]) + (255,)


class Frame:
    def __init__(self) -> None:
        self.im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        self.px = self.im.load()
        self.fx: list[tuple[int, int, tuple[int, ...]]] = []   # effects: drawn after outline

    def rect(self, x: int, y: int, w: int, h: int, c: tuple[int, ...], round_: bool = False
             ) -> None:
        col = _shade(c, 1.0)
        for i in range(x, x + w):
            for j in range(y, y + h):
                if round_ and (i in (x, x + w - 1)) and (j in (y, y + h - 1)):
                    continue
                if 0 <= i < W and 0 <= j < H:
                    self.px[i, j] = col

    def shaded(self, x: int, y: int, w: int, h: int, c: tuple[int, ...]) -> None:
        """A rounded block lit from the top left, like the references."""
        self.rect(x, y, w, h, c, round_=True)
        self.rect(x + w - 2, y + 1, 1, h - 2, _shade(c, 0.78))
        self.rect(x + 1, y + h - 2, w - 2, 1, _shade(c, 0.82))
        self.rect(x + 1, y + 1, w - 3, 1, _shade(c, 1.12))

    def dot(self, x: int, y: int, c: tuple[int, ...]) -> None:
        if 0 <= x < W and 0 <= y < H:
            self.px[x, y] = _shade(c, 1.0)

    def glow(self, x: int, y: int, c: tuple[int, ...]) -> None:
        self.fx.append((x, y, c))

    def finish(self) -> Image.Image:
        src = self.im.copy()
        s = src.load()
        for i in range(W):
            for j in range(H):
                if s[i, j][3] == 0 and any(0 <= i + a < W and 0 <= j + b < H and s[i + a, j + b][3]
                                           for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    self.px[i, j] = OUTLINE
        for x, y, c in self.fx:
            self.dot(x, y, c)
        return self.im


def body(f: Frame, p: dict, who: str, back: bool, lift: int = 0, leg: int = 0,
         arm_l: int = 0, arm_r: int = 0, bob: int = 0) -> None:
    """The robot: legs, torso, arms, head. ``leg`` swings the legs (-1, 0, 1), ``arm_*`` raise
    the arms by that many pixels, ``bob`` moves the upper body down."""
    y0 = bob
    if who == "jarvis":                                             # the cape, behind him
        f.rect(8, 24 + y0, 16, 16, _shade(p["body"], 0.7))
        f.rect(8, 39 + y0, 16, 1, p["trim"])
    f.shaded(11, 35 - max(0, leg) * 3, 4, 7, p["limb"])            # legs
    f.shaded(17, 35 - max(0, -leg) * 3, 4, 7, p["limb"])
    f.rect(10, 41 - max(0, leg) * 3, 6, 2, _shade(p["limb"], 0.6))  # feet
    f.rect(16, 41 - max(0, -leg) * 3, 6, 2, _shade(p["limb"], 0.6))
    coat = who == "researcher"
    f.shaded(10, 23 + y0, 12, 14 if coat else 12, p["body"])         # torso
    if who == "engineer":                                           # hi-vis vest and belt
        f.rect(11, 27 + y0, 10, 1, (255, 222, 60))
        f.rect(11, 30 + y0, 10, 1, (255, 222, 60))
        f.rect(10, 33 + y0, 12, 2, (120, 80, 40))
        f.rect(15, 33 + y0, 2, 2, (220, 190, 90))
    elif not back:
        f.rect(14, 24 + y0, 4, 2, p["trim"])                        # collar
        f.rect(15, 28 + y0, 2, 2, p["eye"])                          # status light
    if arm_l < 6:                                                   # arms (raised: after the head)
        f.shaded(7, 24 + y0 - arm_l, 3, 9, p["limb"])
    if arm_r < 6:
        f.shaded(22, 24 + y0 - arm_r, 3, 9, p["limb"])
    f.rect(14, 21 + y0, 4, 2, _shade(p["limb"], 0.8))               # neck
    f.shaded(8, 8 + y0, 16, 14, p["head"])                          # head
    if not back:
        f.rect(10, 11 + y0, 12, 7, p["visor"])
        f.rect(10, 11 + y0, 12, 1, _shade(p["visor"], 1.8))
    else:
        f.rect(11, 12 + y0, 10, 2, _shade(p["head"], 0.8))          # seam on the back
        f.rect(12, 16 + y0, 8, 1, _shade(p["head"], 0.8))
    if arm_l >= 6:                                                  # an arm up beside the head
        f.shaded(4, 12 + y0, 3, 12, p["limb"])
        f.rect(4, 10 + y0, 3, 3, _shade(p["limb"], 1.1), round_=True)
    if arm_r >= 6:
        f.shaded(25, 12 + y0, 3, 12, p["limb"])
        f.rect(25, 10 + y0, 3, 3, _shade(p["limb"], 1.1), round_=True)
    # role pieces on the head
    if who == "jarvis":
        f.rect(15, 4 + y0, 2, 4, p["trim"])
        for x in range(11, 21):
            f.dot(x, 2 + y0, p["trim"])
        f.dot(10, 3 + y0, p["trim"])
        f.dot(21, 3 + y0, p["trim"])
    elif who == "researcher":
        f.rect(15, 5 + y0, 2, 3, p["limb"])
        f.rect(14, 3 + y0, 4, 3, (255, 236, 120), round_=True)     # the bulb
    elif who == "producer":
        f.rect(7, 13 + y0, 2, 5, (40, 30, 50))                       # headphones
        f.rect(23, 13 + y0, 2, 5, (40, 30, 50))
        f.rect(8, 7 + y0, 16, 1, (40, 30, 50))
        f.rect(8, 5 + y0, 14, 3, (110, 30, 90), round_=True)        # beret
        f.rect(18, 4 + y0, 2, 1, (110, 30, 90))
    elif who == "engineer":
        f.rect(8, 4 + y0, 16, 5, p["trim"], round_=True)             # hard hat
        f.rect(6, 8 + y0, 20, 2, _shade(p["trim"], 0.8))
        f.rect(11, 5 + y0, 10, 1, _shade(p["trim"], 1.2))


def eyes(f: Frame, p: dict, bob: int, kind: str = "open") -> None:
    if kind == "closed":
        f.rect(12, 14 + bob, 3, 1, p["eye"])
        f.rect(17, 14 + bob, 3, 1, p["eye"])
    elif kind == "x":
        for d in range(3):
            f.dot(12 + d, 13 + bob + d, (255, 77, 94))
            f.dot(14 - d, 13 + bob + d, (255, 77, 94))
            f.dot(17 + d, 13 + bob + d, (255, 77, 94))
            f.dot(19 - d, 13 + bob + d, (255, 77, 94))
    else:
        f.rect(12, 13 + bob, 3, 3, p["eye"])
        f.rect(17, 13 + bob, 3, 3, p["eye"])
        f.dot(12, 13 + bob, (255, 255, 255))
        f.dot(17, 13 + bob, (255, 255, 255))


def glasses(f: Frame, bob: int) -> None:
    for cx in (11, 16):
        for i in range(5):
            f.dot(cx + i, 12 + bob, (200, 170, 90))
            f.dot(cx + i, 16 + bob, (200, 170, 90))
        f.dot(cx, 13 + bob, (200, 170, 90))
        f.dot(cx + 4, 13 + bob, (200, 170, 90))


def tool(f: Frame, who: str, p: dict, k: int, bob: int) -> None:
    """What each role works with; ``k`` is the frame (0-3)."""
    if who == "jarvis":                                             # tablet with a plan on it
        f.rect(9, 26 + bob, 14, 8, (20, 30, 50))
        f.rect(10, 27 + bob, 12, 6, (63, 214, 255) if k % 2 == 0 else (120, 230, 255))
        for i in range(k + 1):
            f.rect(11 + i * 3, 31 + bob - i, 2, 1 + i, (255, 207, 77))
    elif who == "researcher":                                       # an open book
        f.rect(8, 27 + bob, 16, 7, (120, 70, 40))
        f.rect(9, 27 + bob, 7, 6, (250, 246, 230))
        f.rect(16, 27 + bob, 7, 6, (250, 246, 230))
        for r in range(3):
            f.rect(10, 28 + bob + r * 2, 5, 1, (150, 150, 160))
            f.rect(17, 28 + bob + r * 2, 5, 1, (150, 150, 160))
        f.rect(16 - 2 + k, 26 + bob, 1, 7, (220, 214, 200))           # the page turning
    elif who == "producer":                                         # a camera at the eye
        f.rect(18, 12 + bob, 9, 6, (35, 35, 45))
        f.rect(21, 13 + bob, 4, 4, (90, 160, 220))
        f.rect(19, 11 + bob, 3, 1, (35, 35, 45))
        if k == 2:
            f.glow(26, 10 + bob, (255, 255, 255))
            f.glow(27, 9 + bob, (255, 255, 200))
            f.glow(25, 9 + bob, (255, 255, 200))
    else:                                                           # a wrench, swung
        y = (22, 25, 28, 25)[k] + bob
        f.rect(24, y, 2, 8, (170, 180, 190))
        f.rect(23, y - 2, 4, 3, (170, 180, 190))
        if k == 2:
            f.glow(27, y + 6, (255, 222, 60))
            f.glow(28, y + 5, (255, 140, 40))


def frames(who: str) -> dict[str, list[Image.Image]]:
    p = CAST[who]
    out: dict[str, list[Image.Image]] = {}

    def make(back: bool = False, **kw: int) -> Frame:
        f = Frame()
        body(f, p, who, back, **kw)
        return f

    out["idle"] = []
    for k in range(2):
        f = make(bob=k)
        eyes(f, p, k, "closed" if k else "open")
        if who == "researcher":
            glasses(f, k)
        out["idle"].append(f.finish())
    for name, back in (("walk_front", False), ("walk_back", True)):
        out[name] = []
        for k in range(4):
            leg, bob = (1, 0, -1, 0)[k], (0, 1, 0, 1)[k]
            f = make(back=back, leg=leg, bob=bob, arm_l=(2, 0, -1, 0)[k] + 1,
                     arm_r=(-1, 0, 2, 0)[k] + 1)
            if not back:
                eyes(f, p, bob)
                if who == "researcher":
                    glasses(f, bob)
            out[name].append(f.finish())
    out["work"] = []
    for k in range(4):
        bob = k % 2
        f = make(bob=bob, arm_l=3, arm_r=3 if who != "engineer" else (6, 3, 0, 3)[k])
        eyes(f, p, bob)
        if who == "researcher":
            glasses(f, bob)
        tool(f, who, p, k, bob)
        out["work"].append(f.finish())
    out["wait"] = []
    for k in range(2):
        f = make(arm_r=10)
        eyes(f, p, 0)
        if who == "researcher":
            glasses(f, 0)
        for j in range(4):                                          # "!" above the hand
            f.glow(30, 0 + j + k, (255, 179, 64))
        f.glow(30, 6 + k, (255, 179, 64))
        out["wait"].append(f.finish())
    out["blocked"] = []
    for k in range(2):
        f = make(bob=2, arm_l=-1, arm_r=-1)
        eyes(f, p, 2, "x")
        for x, y in (((5, 6), (27, 9), (24, 4)), ((26, 5), (6, 10), (9, 3)))[k]:
            f.glow(x, y, (255, 222, 60))
            f.glow(x + 1, y + 1, (255, 77, 94))
        out["blocked"].append(f.finish())
    out["done"] = []
    for k in range(2):
        f = make(arm_l=10, arm_r=10, bob=-k)
        eyes(f, p, -k, "closed")
        for x, y in ((12, 4), (13, 5), (14, 6), (15, 5), (16, 4), (17, 3), (18, 2), (19, 1)):
            f.glow(x, y - k, (70, 242, 164))                        # a check mark over the head
        out["done"].append(f.finish())
    return out


def build() -> tuple[Image.Image, dict]:
    cols = max(n for _, n in ANIMS)
    sheet = Image.new("RGBA", (W * cols, H * len(ANIMS) * len(CAST)), (0, 0, 0, 0))
    meta: dict = {"frame": [W, H], "scale": 3, "anchor": [W // 2, H - 1], "characters": {}}
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
