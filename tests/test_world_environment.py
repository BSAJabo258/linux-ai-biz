"""The world's map and rooms (the owner's prompt 2, 2026-11-20): his department names, the
Delivery and Review Center as one place, rooms that fill the floor without overlapping, and no
wall board across a doorway (the old HQ status board covered one; agents walk door to door)."""

import re
from pathlib import Path

from bau.world import ROOMS

HTML = (Path(__file__).parent.parent / "src/bau/ui/jarvis.html").read_text()


def rooms():
    body = re.search(r"const W_ROOMS = \{(.*?)\};", HTML, re.S).group(1)
    found = re.findall(r"(\w+): \[([\d., ]+)\]", body)
    return {k: tuple(map(float, v.split(","))) for k, v in found}


def test_the_departments_carry_the_owners_names():
    names = {i: n for i, n, _ in ROOMS}
    assert names["forge"] == "Development Forge" and names["studio"] == "Creative Studio"
    assert names["innovation"] == "Innovation Workshop" and names["finance"] == "Finance Office"
    assert names["research"] == "Research library" and names["market"] == "Market"
    assert names["approvals"].startswith("Review")


def test_review_sits_directly_above_delivered_as_one_center():
    r = rooms()
    ax, ay, aw, ah = r["approvals"]
    dx, dy, dw, _ = r["delivery"]
    assert (ax, aw) == (dx, dw) and ay + ah == dy
    assert "DELIVERY & REVIEW CENTER" in HTML


def test_the_rooms_fill_the_floor_and_never_overlap():
    seen = set()
    for x, y, w, h in rooms().values():
        tiles = {(i, j) for i in range(int(x), int(x + w)) for j in range(int(y), int(y + h))}
        assert not tiles & seen
        seen |= tiles
    assert seen == {(i, j) for i in range(16) for j in range(12)}


def doors(rx, ry, rw, rh):
    """Door spans in room terms, the way doors() in the page makes them: one in the middle of
    every 4 tiles of each inside wall (back wall along x, left wall along y)."""
    back = [(2 + 4 * k, 3 + 4 * k) for k in range(int(rw) // 4)] if ry > 0 else []
    left = [(2 + 4 * k, 3 + 4 * k) for k in range(int(rh) // 4)] if rx > 0 else []
    return back, left


def boards():
    """Every wall board in roomProps, with its room: (room, along, start, length)."""
    props = HTML[HTML.index("function roomProps("):HTML.index("function deskSpots(")]
    out = []
    for part in re.split(r'\n  if \(id === "', props)[1:]:
        room = part.split('"', 1)[0]
        for a, b, ln, alongy in re.findall(
                r'wallBoard\(x, rx \+ ([\d.]+), ry \+ ([\d.]+), ([\d.]+), \d+, \d+, "\w+", T, '
                r'light(, true)?\)', part):
            out.append((room, "left", float(b), float(ln)) if alongy
                       else (room, "back", float(a), float(ln)))
    hq = re.search(r"const HQ_BOARD = \[([\d.]+), ([\d.]+)\]", HTML)
    out.append(("hq", "back", float(hq.group(1)), float(hq.group(2))))
    return out


def test_no_board_on_a_wall_crosses_a_doorway():
    r, found = rooms(), boards()
    assert len(found) >= 14                                   # the parser really found them
    for room, along, start, length in found:
        back, left = doors(*r[room])
        for lo, hi in (back if along == "back" else left):
            assert start + length <= lo or start >= hi, (room, along, start, length)
