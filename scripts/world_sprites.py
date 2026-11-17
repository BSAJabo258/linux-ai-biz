"""Draw the operations world's characters as pixel-art sprite sheets
(docs/visual/VISUAL_ART_DIRECTION.md).

Run:  python3 scripts/world_sprites.py
Writes src/bau/ui/world/characters.png (every character, every animation) and characters.json
(where each frame is). Each character is one of the owner's AI assistants, drawn from his
picture of 2026-11-17: glamorous adult women in glossy neon two-piece outfits with chokers and
armbands, each with her own hair, skin, colours and the tool of her job. Same input, same
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
LIPS = (196, 70, 96)
LASH = (30, 20, 24)

# The cast: the real agents (agent folders researcher and producer), Jarvis herself (her
# autopilot does real jobs), and four more looks for the agents the owner adds. All are
# fictional adult women; none is drawn from a real person.
CAST = {
    "jarvis": {"skin": (196, 136, 98), "hair": (24, 18, 22), "suit": (22, 24, 34),
               "trim": (63, 214, 255), "eye": (90, 60, 40), "long": 30, "bun": False,
               "glasses": False,
               "role": "the lead: long black hair, black and cyan glossy two-piece, glowing "
                       "choker, a tablet she plans on"},
    "researcher": {"skin": (178, 118, 84), "hair": (34, 24, 26), "suit": (40, 70, 200),
                   "trim": (120, 200, 255), "eye": (70, 50, 36), "long": 0, "bun": True,
                   "glasses": True,
                   "role": "dark hair up in a bun, glasses, royal-blue two-piece, reads a book"},
    "producer": {"skin": (240, 196, 170), "hair": (190, 40, 36), "suit": (170, 20, 34),
                 "trim": (255, 110, 120), "eye": (60, 110, 70), "long": 26, "bun": False,
                 "glasses": False,
                 "role": "long red hair, red glossy two-piece, films with a camera"},
    "engineer": {"skin": (228, 182, 150), "hair": (246, 222, 150), "suit": (34, 30, 30),
                 "trim": (255, 200, 70), "eye": (60, 100, 150), "long": 24, "bun": False,
                 "glasses": True,
                 "role": "long blonde hair, glasses, black and gold two-piece, a gold wrench"},
    # More looks from the same picture, for agents without one of their own (world.py)
    "coordinator": {"skin": (214, 160, 120), "hair": (20, 16, 26), "suit": (120, 50, 190),
                    "trim": (200, 140, 255), "eye": (70, 50, 40), "long": 28, "bun": False,
                    "glasses": False,
                    "role": "long black hair, violet glossy two-piece and boots, a tablet"},
    "analyst": {"skin": (120, 74, 50), "hair": (30, 20, 18), "suit": (200, 150, 40),
                "trim": (255, 236, 150), "eye": (60, 40, 30), "long": 20, "bun": False,
                "glasses": False, "curls": True,
                "role": "big dark curls, gold and bronze two-piece, a tablet"},
    "architect": {"skin": (236, 200, 176), "hair": (236, 236, 244), "suit": (210, 220, 236),
                  "trim": (120, 220, 255), "eye": (80, 120, 170), "long": 26, "bun": False,
                  "glasses": False,
                  "role": "long platinum hair, white glossy two-piece, a tablet"},
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
        self.rect(x + w - 1, y + 1, 1, h - 2, _shade(c, 0.78))
        self.rect(x + 1, y + 1, max(1, w - 2), 1, _shade(c, 1.12))

    def gloss(self, x: int, y: int, w: int, h: int, c: tuple[int, ...]) -> None:
        """A glossy piece of the outfit: the colour, a dark edge and a bright shine."""
        self.rect(x, y, w, h, c, round_=w > 2 and h > 2)
        self.rect(x, y + h - 1, w, 1, _shade(c, 0.6))
        self.dot(x + 1, y, _shade(c, 2.2) if max(c[:3]) < 60 else _shade(c, 1.45))

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
    """The woman: hair behind, legs in glossy boots, the two-piece, arms, head and hair.
    ``leg`` swings the legs (-1, 0, 1), ``arm_*`` raise the arms by that many pixels, ``bob``
    moves the upper body down."""
    y0 = bob
    sk, hair, suit, trim = p["skin"], p["hair"], p["suit"], p["trim"]
    if p["long"]:                                                   # long hair, behind her
        f.rect(11, 8 + y0, 10, p["long"] - 8 - (0 if back else 4), hair, round_=True)
    for x, up in ((12, max(0, leg)), (17, max(0, -leg))):           # legs
        f.shaded(x, 28 - up * 2, 3, 7, sk)                          # thighs
        f.gloss(x, 34 - up * 2, 3, 7, suit)                         # boots
        f.rect(x, 34 - up * 2, 3, 1, trim)                          # boot top
        f.rect(x + (0 if x < 16 else 1), 41 - up * 2, 2, 2, _shade(suit, 0.7))  # heel
    f.shaded(11, 24 + y0, 10, 5, sk)                                # hips
    f.gloss(11, 24 + y0, 10, 3, suit)                               # bottom
    f.rect(11, 24 + y0, 10, 1, trim)                                # waistband glow
    f.shaded(13, 20 + y0, 6, 5, sk)                                 # waist
    f.dot(15, 22 + y0, _shade(sk, 0.8))                             # navel
    f.shaded(11, 16 + y0, 10, 5, sk)                                # shoulders and chest
    if back:
        f.rect(11, 18 + y0, 10, 1, suit)                            # the top's strap
    else:
        f.gloss(11, 17 + y0, 5, 3, suit)                            # the top
        f.gloss(16, 17 + y0, 5, 3, suit)
        f.dot(15, 17 + y0, trim)
        f.dot(16, 17 + y0, trim)
    for x, a in ((9, arm_l), (21, arm_r)):                          # arms (raised: after the head)
        if a < 6:
            f.shaded(x, 16 + y0 - a, 2, 10, sk)
            f.rect(x, 19 + y0 - a, 2, 1, suit)                      # armband
            f.dot(x, 19 + y0 - a, trim)
    f.rect(15, 14 + y0, 2, 2, sk)                                   # neck
    f.rect(14, 15 + y0, 4, 1, trim)                                 # choker
    f.shaded(12, 5 + y0, 8, 10, sk)                                 # face
    f.rect(11, 4 + y0, 10, 3, hair, round_=True)                    # hair on top
    if back:
        f.rect(12, 5 + y0, 8, 10, hair, round_=True)
    else:
        f.rect(11, 6 + y0, 2, 7 if p["long"] else 3, hair)          # hair at the sides
        f.rect(19, 6 + y0, 2, 7 if p["long"] else 3, hair)
        f.rect(13, 6 + y0, 3, 1, hair)                              # a swept fringe
    if p.get("curls"):                                              # curls round the head
        for x, y in ((10, 6), (21, 6), (10, 10), (21, 10), (11, 3), (20, 3), (15, 2), (10, 14),
                     (21, 14)):
            f.rect(x, y + y0, 2, 2, hair, round_=False)
    if p["bun"]:
        f.rect(13, 1 + y0, 6, 4, hair, round_=True)
        f.dot(14, 2 + y0, _shade(hair, 2.0))
    if who == "jarvis" and not back:                                # her mark on the top
        f.glow(15, 19 + y0, trim)
    for x, a in ((9, arm_l), (21, arm_r)):                          # an arm up beside the head
        if a >= 6:
            f.shaded(x, 4 + y0, 2, 12, sk)
            f.rect(x, 9 + y0, 2, 1, suit)


def eyes(f: Frame, p: dict, bob: int, kind: str = "open") -> None:
    if kind == "closed":
        f.rect(13, 10 + bob, 2, 1, LASH)
        f.rect(17, 10 + bob, 2, 1, LASH)
    elif kind == "x":
        for d in range(2):
            f.dot(13 + d, 9 + bob + d, (255, 77, 94))
            f.dot(14 - d, 9 + bob + d, (255, 77, 94))
            f.dot(17 + d, 9 + bob + d, (255, 77, 94))
            f.dot(18 - d, 9 + bob + d, (255, 77, 94))
    else:
        f.rect(13, 9 + bob, 2, 1, LASH)                             # lashes
        f.rect(17, 9 + bob, 2, 1, LASH)
        f.dot(13, 10 + bob, (250, 250, 250))
        f.dot(14, 10 + bob, p["eye"])
        f.dot(17, 10 + bob, p["eye"])
        f.dot(18, 10 + bob, (250, 250, 250))
        f.dot(12, 9 + bob, LASH)                                    # winged liner
        f.dot(19, 9 + bob, LASH)
    f.rect(15, 13 + bob, 2, 1, LIPS)


def glasses(f: Frame, bob: int) -> None:
    """Thin frames round the eyes, so the eyes still show."""
    for cx in (12, 16):
        f.rect(cx, 8 + bob, 4, 1, (60, 40, 40))
        f.dot(cx, 9 + bob, (60, 40, 40))
        f.dot(cx + 3, 9 + bob, (60, 40, 40))
        f.dot(cx, 10 + bob, (60, 40, 40))
        f.dot(cx + 3, 10 + bob, (60, 40, 40))
        f.rect(cx + 1, 11 + bob, 2, 1, (60, 40, 40))


def tool(f: Frame, who: str, p: dict, k: int, bob: int) -> None:
    """What each assistant works with; ``k`` is the frame (0-3)."""
    if who == "jarvis":                                             # tablet with a plan on it
        f.rect(9, 21 + bob, 14, 7, (20, 30, 50))
        f.rect(10, 22 + bob, 12, 5, (63, 214, 255) if k % 2 == 0 else (120, 230, 255))
        for i in range(k + 1):
            f.rect(11 + i * 3, 25 + bob - i, 2, 1 + i, (255, 255, 255))
    elif who == "researcher":                                       # an open book
        f.rect(9, 21 + bob, 14, 6, (60, 40, 90))
        f.rect(10, 21 + bob, 6, 5, (250, 246, 230))
        f.rect(16, 21 + bob, 6, 5, (250, 246, 230))
        for r in range(2):
            f.rect(11, 22 + bob + r * 2, 4, 1, (150, 150, 170))
            f.rect(17, 22 + bob + r * 2, 4, 1, (150, 150, 170))
        f.rect(14 + k, 20 + bob, 1, 6, (220, 214, 200))             # the page turning
    elif who == "producer":                                         # a camera at the eye
        f.rect(18, 7 + bob, 9, 6, (35, 35, 45))
        f.rect(21, 8 + bob, 4, 4, (90, 160, 220))
        f.rect(19, 6 + bob, 3, 1, (35, 35, 45))
        if k == 2:
            f.glow(26, 5 + bob, (255, 255, 255))
            f.glow(27, 4 + bob, (255, 255, 200))
            f.glow(25, 4 + bob, (255, 255, 200))
    elif who != "engineer":                                         # a tablet in her colour
        f.rect(9, 21 + bob, 14, 7, (20, 24, 40))
        f.rect(10, 22 + bob, 12, 5, p["trim"] if k % 2 == 0 else _shade(p["trim"], 1.2))
        f.rect(11 + k * 2, 24 + bob, 3, 1, (255, 255, 255))
    else:                                                           # a gold wrench, swung
        y = (12, 15, 18, 15)[k] + bob
        f.rect(23, y, 2, 8, p["trim"])
        f.rect(22, y - 2, 4, 3, p["trim"])
        if k == 2:
            f.glow(26, y + 6, (255, 240, 160))
            f.glow(27, y + 5, (255, 200, 70))


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
        if p["glasses"]:
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
                if p["glasses"]:
                    glasses(f, bob)
            out[name].append(f.finish())
    out["work"] = []
    for k in range(4):
        bob = k % 2
        f = make(bob=bob, arm_l=3, arm_r=3 if who != "engineer" else (6, 3, 0, 3)[k])
        eyes(f, p, bob)
        if p["glasses"]:
            glasses(f, bob)
        tool(f, who, p, k, bob)
        out["work"].append(f.finish())
    out["wait"] = []
    for k in range(2):
        f = make(arm_r=10)
        eyes(f, p, 0)
        if p["glasses"]:
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
