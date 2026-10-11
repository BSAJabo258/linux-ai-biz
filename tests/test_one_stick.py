"""One stick: USB #1 carries the BAU payload, the installer copies it onto the new system."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRESEED = ROOT / "installer" / "preseed" / "bau.preseed"
needs_linux = pytest.mark.skipif(
    not shutil.which("sh") or not shutil.which("sha256sum"), reason="needs sh and sha256sum")


def _payload(where: Path) -> Path:
    p = where / "BAU-PAYLOAD"
    (p / "docs").mkdir(parents=True)
    (p / "install.sh").write_text("#!/bin/sh\n")
    (p / "docs" / "INSTALL.md").write_text("guide\n")
    # Written beside the folder first, as make-payload.sh does, so it never lists itself.
    subprocess.run("find . -type f -print0 | sort -z | xargs -0 sha256sum > ../sums"
                   " && mv ../sums SHA256SUMS", shell=True, cwd=p, check=True)
    return p


def _late_command(tmp_path: Path) -> tuple[Path, Path]:
    """Run the preseed's late_command against fake /cdrom and /target folders."""
    cdrom, target = tmp_path / "cdrom", tmp_path / "target"
    (cdrom / "bau").mkdir(parents=True)
    (cdrom / "bau" / "firstboot-setup.sh").write_text("true\n")   # tested separately
    target.mkdir()
    fake = tmp_path / "bin"
    fake.mkdir()
    # in-target runs a command inside /target; here: rewrite its /opt paths instead of chroot.
    (fake / "in-target").write_text(
        f'#!/bin/sh\nexec "$1" "$2" "$(printf %s "$3" | sed "s|/opt/|{target}/opt/|g")"\n')
    (fake / "in-target").chmod(0o755)
    text = PRESEED.read_text()
    cmd = re.search(r"preseed/late_command string (.*?)\n(?!\s)", text, re.S).group(1)
    cmd = cmd.replace("\\\n", " ").replace("/cdrom", str(cdrom)).replace("/target", str(target))
    cmd = cmd.replace("in-target /bin/sh /opt/", f"in-target /bin/sh {target}/opt/")
    r = subprocess.run(["sh", "-c", cmd], env={"PATH": f"{fake}:/usr/bin:/bin"},
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return cdrom, target


@needs_linux
def test_installer_copies_and_checks_the_payload(tmp_path):
    _payload(tmp_path / "cdrom")
    _, target = _late_command(tmp_path)
    assert (target / "opt" / "bau-payload" / "install.sh").exists()
    assert (target / "opt" / "bau-payload" / "docs" / "INSTALL.md").exists()


@needs_linux
def test_installer_deletes_a_payload_that_fails_its_checksums(tmp_path):
    p = _payload(tmp_path / "cdrom")
    (p / "install.sh").write_text("#!/bin/sh\necho tampered\n")
    _, target = _late_command(tmp_path)
    assert not (target / "opt" / "bau-payload").exists()


@needs_linux
def test_two_stick_image_still_installs_without_a_payload(tmp_path):
    _, target = _late_command(tmp_path)
    assert (target / "opt" / "bau-bootstrap").is_dir()
    assert not (target / "opt" / "bau-payload").exists()


def test_first_boot_notice_points_at_the_copied_payload_and_install_sh_removes_it():
    fb = (ROOT / "installer" / "firstboot" / "firstboot-setup.sh").read_text()
    assert "sudo bash /opt/bau-payload/install.sh" in fb
    sh = (ROOT / "installer" / "payload" / "install.sh").read_text()
    start, end = re.search(r"sed -i '/(.*?)/,/(.*?)/d' /etc/motd", sh).groups()
    end = end.replace("\\.", ".")
    for notice in re.findall(r"<<'EOF'\n(.*?)\nEOF", fb, re.S):
        assert start in notice and end in notice


@pytest.mark.skipif(not all(shutil.which(t) for t in ("bash", "sha256sum", "xorriso", "gpg")),
                    reason="needs bash, sha256sum, xorriso, gpg")
def test_image_builder_refuses_a_payload_that_fails_its_checksums(tmp_path):
    p = _payload(tmp_path)
    (p / "install.sh").write_text("#!/bin/sh\necho tampered\n")
    r = subprocess.run(["bash", str(ROOT / "installer" / "build-usb-image.sh"), "--payload",
                        str(p), "--out", str(tmp_path / "out")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode != 0
    assert "does not match its SHA256SUMS" in r.stderr + r.stdout
