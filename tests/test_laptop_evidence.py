"""The Linux laptop check's verdict and its "what BAU would find in place" evidence.

The check used to list hardware and stop. It now ends with the same three verdicts as the
Windows script and, before the summary, says whether this machine could run BAU: tools,
listening ports, bau-*.service units. Everything here runs the real script; only its inputs
are made up, so the promises tested are the ones the owner relies on: a shareable summary
stays free of names/addresses/paths, secret files are opened by nothing, and process
command lines (which carry tokens) are never read.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SH = ROOT / "installer" / "bau-laptop-check.sh"
LIB = ROOT / "installer" / "lib" / "laptop-evidence.sh"
VERDICTS = ("READY", "READY, AFTER THESE STEPS", "NOT READY")


def run_check(tmp_path, env_extra=None, path_dir=None):
    """Run the check into a temp folder; return (summary, full) as text."""
    out = tmp_path / "out"
    env = dict(os.environ)
    env["BAU_ETC"] = str(tmp_path / "etc-bau")          # never read the host's real secrets
    env.update(env_extra or {})
    if path_dir:
        env["PATH"] = f"{path_dir}{os.pathsep}{env['PATH']}"
    r = subprocess.run(["bash", str(SH), str(out)], capture_output=True, text=True,
                       timeout=180, env=env)
    assert r.returncode == 0, r.stderr
    return ((out / "BAU-LAPTOP-SUMMARY-LINUX.txt").read_text(),
            (out / "BAU-LAPTOP-FULL-LINUX.txt").read_text())


def test_verdict_comes_first_and_each_reason_says_what_to_do(tmp_path):
    summary, _ = run_check(tmp_path)
    verdict = next(ln for ln in summary.splitlines() if ln.startswith("VERDICT: "))
    assert verdict.removeprefix("VERDICT: ") in VERDICTS
    assert summary.splitlines()[2] == verdict                     # right under the title
    reasons = [ln for ln in summary.splitlines()
               if ln.startswith(("  BLOCKER: ", "  DO FIRST: "))]
    if verdict.endswith("NOT READY"):
        assert any(ln.startswith("  BLOCKER: ") for ln in reasons)
    else:
        assert not any(ln.startswith("  BLOCKER: ") for ln in reasons)
    if "AFTER THESE STEPS" in verdict:
        assert any(ln.startswith("  DO FIRST: ") for ln in reasons)
    assert all(ln.split(":", 1)[1].strip() for ln in reasons)


def test_the_summary_is_shareable_but_the_full_report_keeps_the_details(tmp_path):
    summary, full = run_check(tmp_path)
    assert "BAU on this machine:" in summary
    assert re.search(r"^  python3: ", summary, re.M)
    assert re.search(r"^  listening ports: ", summary, re.M)
    for private in (str(tmp_path), "127.0.0.1", "192.168."):
        assert private not in summary, private
    for heading in ("### BAU checkout", "### bau services", "### listening addresses",
                    "### secret files", "### process names"):
        assert heading in full, heading
    assert str(tmp_path) in full                                  # paths only in the private file


def test_secret_files_are_noted_with_their_mode_but_never_opened(tmp_path):
    etc = tmp_path / "etc-bau"
    etc.mkdir()
    secret = etc / "jarvis.env"
    secret.write_text("OPENAI_API_KEY=sk-CANARY-NEVER-COPIED\n")
    secret.chmod(0o600)
    loose = etc / "loose.env"
    loose.write_text("ANTHROPIC_API_KEY=sk-CANARY-ALSO-NEVER\n")
    loose.chmod(0o644)
    summary, full = run_check(tmp_path)
    assert "CANARY" not in summary and "CANARY" not in full
    assert f"  600 {secret}" in full
    assert f"  644 {loose}" in full and "chmod 600" in full


def test_process_command_lines_are_never_printed(tmp_path):
    p = subprocess.Popen(["sleep", "60", "--BAU-ARGV-CANARY"])     # the token lives in argv
    try:
        summary, full = run_check(tmp_path)
    finally:
        p.kill()
        p.wait(timeout=30)
    assert "BAU-ARGV-CANARY" not in summary and "BAU-ARGV-CANARY" not in full
    assert re.search(r"^\s+\d+ sleep$", full, re.M)                # names only


def test_a_dirty_checkout_is_reported_with_branch_commit_and_changes(tmp_path):
    git = shutil.which("git")
    if not git:
        pytest.skip("needs git")
    repo = tmp_path / "bau-repo"
    repo.mkdir()
    who = ["-c", "user.name=BAU test", "-c", "user.email=test@example.invalid"]

    def run(*args):
        return subprocess.run([git, "-C", str(repo), *who, *args], check=True,
                              capture_output=True, text=True)

    run("init", "-q", "-b", "main")
    (repo / "README.md").write_text("hello\n")
    run("add", "README.md")
    run("commit", "-q", "-m", "first commit on a test repo")
    (repo / "README.md").write_text("hello, changed\n")
    _, full = run_check(tmp_path, {"BAU_DIR": str(repo), "HOME": str(tmp_path / "home")})
    assert f"{repo}: main " in full
    assert "1 changed file(s)" in full
    assert "first commit on a test repo" in full


def test_a_device_without_a_driver_becomes_a_step(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    lspci = bin_dir / "lspci"
    lspci.write_text("#!/bin/sh\ncat <<'EOF'\n"
                     "00:14.3 Network controller [0280]: Intel Corporation Wi-Fi [8086:a0f0]\n"
                     "\tSubsystem: Intel Corporation Device [8086:0074]\n"
                     "EOF\n")
    lspci.chmod(0o755)
    summary, _ = run_check(tmp_path, path_dir=str(bin_dir))
    assert "NO DRIVER LOADED" in summary
    assert "DO FIRST: 1 device(s) with NO DRIVER LOADED" in summary


def test_the_evidence_only_reads():
    text = "\n".join(ln for ln in LIB.read_text().splitlines()
                     if not ln.lstrip().startswith("#"))
    for pattern in (r"\b(mkfs|wipefs|parted|sfdisk)\b", r"\bdd\s+if=", r"\brm\s+-rf?\s+/",
                    r"bcdedit\s+/set", r"\breg\s+(add|delete)"):
        assert not re.search(pattern, text, re.I), pattern


def test_the_evidence_ships_on_the_stick_and_is_linted():
    assert "lib/laptop-evidence.sh" in (ROOT / "installer" / "make-payload.sh").read_text()
    assert "installer/lib/*.sh" in (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    if not shutil.which("shellcheck"):
        pytest.skip("needs shellcheck")
    r = subprocess.run(["shellcheck", "-x", str(SH), str(LIB)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_a_script_copied_alone_says_the_verdict_is_unknown(tmp_path):
    alone = tmp_path / "alone"
    alone.mkdir()
    shutil.copy(SH, alone / "bau-laptop-check.sh")
    out = tmp_path / "out-alone"
    r = subprocess.run(["bash", str(alone / "bau-laptop-check.sh"), str(out)],
                       capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr
    summary = (out / "BAU-LAPTOP-SUMMARY-LINUX.txt").read_text()
    assert "VERDICT: unknown" in summary and "laptop-evidence.sh is missing" in summary
