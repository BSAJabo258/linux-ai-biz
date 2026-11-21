"""The watch (the owner's plan, 2026-11-20: "like UptimeRobot ... problems pop up as cards"):
the Governor's 10-minute tick also watches the money machine's links and services, and each
open problem pops up in Jarvis with its fix. Fakes only."""

import os
import stat

from bau.audit import AuditLog
from bau.governor import Governor


def link(name, ok, found="", fix="do the fix"):
    return {"link": name, "ok": ok, "found": found, "fix": "" if ok else fix}


def gov(home, links, **kw):
    kw.setdefault("systemctl", "")
    return Governor(home, audit=AuditLog(home / "audit" / "chain.jsonl", key=b""),
                    money=lambda: links, **kw)


def test_a_money_link_that_breaks_is_a_finding_with_its_fix(tmp_path):
    links = [link("Fanvue connected", True), link("prices", False, "not set")]
    def money(new):
        return [f for f in new if f["check"] == "money"]
    assert money(gov(tmp_path, links).tick()["new"]) == []   # never set up: its card says it
    links[0] = link("Fanvue connected", False, "not connected", "bau fanvue login")
    new = money(gov(tmp_path, links).tick()["new"])
    assert [f["subject"] for f in new] == ["Fanvue connected"]
    assert "bau fanvue login" in new[0]["detail"]
    assert money(gov(tmp_path, links).tick()["new"]) == []   # said once while it lasts
    links[0] = link("Fanvue connected", True)
    gov(tmp_path, links).tick()
    assert not [f for f in gov(tmp_path, links).open_findings() if f["check"] == "money"]


def test_a_failed_picture_maker_is_caught(tmp_path):
    fake = tmp_path / "systemctl"
    fake.write_text('#!/bin/sh\n[ "$2" = bau-pictures.service ] && echo failed && exit 3\n'
                    'echo active\n')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    new = gov(tmp_path, [], systemctl=os.fspath(fake)).tick()["new"]
    assert [f["subject"] for f in new if f["check"] == "services"] == ["bau-pictures.service"]


def test_each_problem_pops_up_once_in_jarvis_until_seen(tmp_path):
    from bau.assistant import Assistant
    links = [link("pictures (ComfyUI on this computer)", True)]
    gov(tmp_path, links).tick()
    links[0] = link("pictures (ComfyUI on this computer)", False, "installed, not running",
                    "sudo systemctl start bau-pictures.service")
    gov(tmp_path, links).tick()
    j = Assistant(tmp_path)
    cards = [p for p in j.setup_waiting() if p["tool"] == "governor_finding"]
    assert len(cards) == 1 and "sudo systemctl start bau-pictures.service" in cards[0]["summary"]
    assert [p for p in j.setup_waiting() if p["tool"] == "governor_finding"] == cards
    assert j.confirm(cards[0]["id"], True, "human:owner")["done"]
    assert not [p for p in j.setup_waiting() if p["tool"] == "governor_finding"]
    assert not [f for f in gov(tmp_path, links).open_findings() if f["check"] == "money"]
