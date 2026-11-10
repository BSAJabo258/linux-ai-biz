"""BAU's repeating timers run on the clock (OnCalendar), never only "N minutes after the last
run" (OnUnitActiveSec): after the desktop's reboot on 2026-11-10 both the Governor and the
autopilot timers showed no next run and stopped for hours without a word."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_repeating_timers_are_on_the_clock():
    found = list(ROOT.glob("installer/**/*.timer")) + list(ROOT.glob("installer/**/*.sh")) + \
        list(ROOT.glob("src/bau/data/setup/*.sh")) + list(ROOT.glob("image/**/*.timer"))
    assert found
    stall = [str(p.relative_to(ROOT)) for p in found if "OnUnitActiveSec" in p.read_text()]
    assert stall == []
    for name in ("bau-governor.timer", "bau-autopilot.timer"):
        assert "OnCalendar=" in (ROOT / "installer/payload/systemd" / name).read_text()
