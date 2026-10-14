"""The full stick: one image that runs My Jarvis from the stick AND installs BAU on the
laptop. Debian's installer is built into the live image (live-build --debian-installer
live): it copies the tested live system to the disk, with the same rules as the BAU
installer stick - the owner picks and confirms the disk, chooses the passphrase and the
password - then puts the BAU payload carried on the stick into /opt/bau-payload, checked.
Written before the code it tests."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LB = ROOT / "image" / "live-build"
LIVE_PRESEED = LB / "config" / "includes.installer" / "preseed.cfg"
STICK_PRESEED = ROOT / "installer" / "preseed" / "bau.preseed"
needs_linux = pytest.mark.skipif(not all(shutil.which(t) for t in ("sh", "sha256sum")),
                                 reason="needs sh and sha256sum")


def lines(path, prefix):
    return sorted(ln.strip() for ln in path.read_text().splitlines()
                  if ln.strip().startswith(prefix))


# ------------------------------------------------------------------ the image has an installer

def test_live_image_is_built_with_the_debian_installer_in_live_mode():
    cfg = (LB / "auto" / "config").read_text()
    assert "--debian-installer live" in cfg and "--debian-installer none" not in cfg
    assert "--debian-installer-gui true" in cfg
    assert "persistence-encryption=lukslabel" in cfg            # live mode unchanged


def test_boot_menu_offers_install_next_to_my_jarvis():
    grub = (LB / "grub.cfg").read_text()
    entries = re.findall(r'menuentry "([^"]+)"', grub)
    assert entries[0] == "My Jarvis"                           # running live stays the default
    install = next(e for e in entries if e.startswith("Install BAU"))
    block = grub[grub.index(install):].split("}", 1)[0]
    assert "@KERNEL_GI@" in block and "@INITRD_GI@" in block and "@APPEND_INSTALL@" in block


# ------------------------------------------------------------------ the installer's answers

def test_installer_never_chooses_the_disk_or_holds_a_secret():
    text = LIVE_PRESEED.read_text()
    for never in ("partman-auto/disk", "partman/confirm ", "partman/confirm_write_new_label",
                  "partman-lvm/confirm", "partman-crypto/passphrase", "passwd/user-password",
                  "passwd/root-password", "time/zone"):
        assert never not in text, never


def test_installer_sets_up_the_disk_and_accounts_exactly_like_the_bau_stick():
    for prefix in ("d-i partman-auto", "d-i passwd/", "d-i clock-setup/",
                   "d-i grub-installer/"):
        assert lines(LIVE_PRESEED, prefix) == lines(STICK_PRESEED, prefix), prefix


def test_installer_asks_where_the_boot_loader_goes():
    """'bootdev default' means the first disk. On a laptop installing onto a USB disk the
    first disk can be the install stick itself: GRUB then fails ("grub-install /dev/sda
    failed", seen on the owner's XPS 13). The owner picks it, like the install disk."""
    for preseed in (LIVE_PRESEED, STICK_PRESEED):
        assert "grub-installer/bootdev" not in preseed.read_text(), preseed


def test_boot_loader_also_goes_where_any_uefi_pc_finds_it():
    # The fallback path EFI/BOOT/BOOTX64.EFI: a USB disk starts from F12 on any UEFI PC,
    # even when the firmware forgets or refuses the boot entry.
    for preseed in (LIVE_PRESEED, STICK_PRESEED):
        assert "d-i grub-installer/force-efi-extra-removable boolean true" in \
            preseed.read_text(), preseed


def test_docs_say_which_disk_gets_the_boot_loader_and_how_to_recover():
    doc = (ROOT / "docs" / "LIVE-USB.md").read_text()
    assert "Install the GRUB boot loader" in doc
    assert "lsblk -o NAME,SIZE,MODEL" in doc                # how to tell the disks apart
    assert "grub-install" in doc and "Continue without boot loader" in doc


def test_installer_knows_the_release_without_a_network():
    """Debian's live installer reads the release name from the mirror it contacted. With no
    network it never contacts one, and "Install the system" stops with "Debootstrap Error:
    Failed to determine the codename for the release" (seen on the owner's XPS 13). The
    preseed names the release the image is built from, so installing works offline."""
    dist = re.search(r"--distribution (\S+)", (LB / "auto" / "config").read_text()).group(1)
    text = LIVE_PRESEED.read_text()
    assert f"d-i mirror/codename string {dist}" in text
    assert f"d-i mirror/suite string {dist}" in text


def test_docs_say_what_to_do_when_the_installer_wants_a_network():
    doc = (ROOT / "docs" / "LIVE-USB.md").read_text()
    assert "Failed to determine the codename" in doc
    assert "USB tethering" in doc and "Configure the network" in doc


def test_installer_copies_the_tested_live_system_instead_of_downloading_a_desktop():
    text = LIVE_PRESEED.read_text()
    assert "gnome-desktop" not in text
    assert re.search(r"^tasksel tasksel/first multiselect\s*$", text, re.M)


# ------------------------------------------------------------------ what the installer leaves

def _payload(where: Path) -> Path:
    p = where / "BAU-PAYLOAD"
    (p / "docs").mkdir(parents=True)
    (p / "install.sh").write_text("#!/bin/sh\n")
    subprocess.run("find . -type f -print0 | sort -z | xargs -0 sha256sum > ../sums"
                   " && mv ../sums SHA256SUMS", shell=True, cwd=p, check=True)
    return p


def _late_command(tmp_path: Path) -> Path:
    """Run the live preseed's late_command against fake /cdrom and /target folders."""
    cdrom, target = tmp_path / "cdrom", tmp_path / "target"
    (cdrom / "bau").mkdir(parents=True, exist_ok=True)
    shutil.copy(LB / "live-to-disk.sh", cdrom / "bau" / "live-to-disk.sh")
    etc = target / "etc"
    for unit in ("bau-ui.service", "bau-llm.service"):
        d = etc / "systemd" / "system" / f"{unit}.d"
        d.mkdir(parents=True)
        (d / "live.conf").write_text("[Unit]\nConditionPathExists=/run/bau-live/private\n")
    (etc / "systemd" / "system" / "bau-live-init.service").write_text("[Unit]\n")
    wants = etc / "systemd" / "system" / "multi-user.target.wants"
    timers = etc / "systemd" / "system" / "timers.target.wants"
    wants.mkdir()
    timers.mkdir()
    for u in ("bau-recover.service", "bau-ui.service", "bau-llm.service",
              "bau-live-init.service", "ssh.service"):
        (wants / u).symlink_to(f"/etc/systemd/system/{u}")
    for u in ("bau-governor.timer", "bau-regwatch.timer"):
        (timers / u).symlink_to(f"/etc/systemd/system/{u}")
    (etc / "xdg" / "autostart").mkdir(parents=True)
    (etc / "xdg" / "autostart" / "my-jarvis-setup.desktop").write_text("[Desktop Entry]\n")
    fake = tmp_path / "bin"
    fake.mkdir()
    # in-target runs a command inside /target: here, rewrite its absolute paths instead.
    (fake / "in-target").write_text(
        f'#!/bin/sh\nexec "$1" "$2" "$(printf %s "$3" | sed "s|/opt/|{target}/opt/|g")"\n')
    (fake / "in-target").chmod(0o755)
    cmd = re.search(r"preseed/late_command string (.*?)\n(?!\s)", LIVE_PRESEED.read_text(),
                    re.S).group(1)
    cmd = cmd.replace("\\\n", " ").replace("/cdrom", str(cdrom)).replace("/target", str(target))
    cmd = cmd.replace("in-target /bin/sh /opt/", f"in-target /bin/sh {target}/opt/")
    # The real firstboot-setup.sh is tested with the BAU stick; here it only leaves a mark.
    (cdrom / "bau" / "firstboot-setup.sh").write_text(
        f"touch {target}/opt/bau-bootstrap/firstboot-ran\n")
    r = subprocess.run(["sh", "-c", cmd], env={"PATH": f"{fake}:/usr/bin:/bin"},
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return target


@needs_linux
def test_installed_laptop_gets_the_checked_payload_and_first_boot_setup(tmp_path):
    _payload(tmp_path / "cdrom")
    target = _late_command(tmp_path)
    assert (target / "opt" / "bau-payload" / "install.sh").is_file()
    assert (target / "opt" / "bau-bootstrap" / "firstboot-ran").exists()


@needs_linux
def test_a_payload_that_fails_its_checksums_is_not_installed(tmp_path):
    p = _payload(tmp_path / "cdrom")
    (p / "install.sh").write_text("#!/bin/sh\necho tampered\n")
    target = _late_command(tmp_path)
    assert not (target / "opt" / "bau-payload").exists()


@needs_linux
def test_live_only_startup_is_removed_from_the_installed_laptop(tmp_path):
    _payload(tmp_path / "cdrom")
    target = _late_command(tmp_path)
    units = target / "etc" / "systemd" / "system"
    assert not list(units.rglob("live.conf"))          # BAU's services can start on the laptop
    assert not (units / "bau-live-init.service").exists()
    # BAU's own services wait for install.sh (it makes their keys, then enables them);
    # found failing in the first VM install of the full stick (2026-10-12).
    enabled = {p.name for p in units.glob("*.wants/*")}
    assert enabled == {"bau-llm.service", "ssh.service"}       # llm waits on /etc/bau/llm.env
    assert not (target / "etc" / "xdg" / "autostart" / "my-jarvis-setup.desktop").exists()


def test_live_to_disk_only_touches_what_the_live_image_added():
    script = (LB / "live-to-disk.sh").read_text()
    assert "rm -rf /" not in script.replace("rm -rf /target", "")
    for gone in ("live.conf", "bau-live-init", "my-jarvis-setup.desktop"):
        assert gone in script


# ------------------------------------------------------------------ the build fills the stick

def test_build_puts_the_checked_payload_and_bootstrap_on_the_stick():
    sh = (ROOT / "image" / "build-live.sh").read_text()
    assert "BAU-PAYLOAD\" \"${bin}/BAU-PAYLOAD\"" in sh and "includes.binary" in sh
    assert "sha256sum --quiet --strict -c SHA256SUMS" in sh     # never a payload that fails
    assert "${bin}/bau" in sh
    for f in ("firstboot-setup.sh", "live-to-disk.sh", "hardening"):
        assert f in sh, f


@pytest.mark.skipif(not shutil.which("shellcheck"), reason="needs shellcheck")
def test_scripts_pass_shellcheck():
    r = subprocess.run(["shellcheck", "-x", str(LB / "live-to-disk.sh"),
                        str(ROOT / "image" / "build-live.sh")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_owner_guide_explains_both_choices():
    doc = (ROOT / "docs" / "LIVE-USB.md").read_text()
    assert "Install BAU on this laptop" in doc and "/opt/bau-payload/install.sh" in doc


def test_the_stick_carries_every_package_install_sh_needs():
    """So the laptop is finished with no network (install.sh --offline); found on the
    owner's XPS 13, whose Wi-Fi was not working after the install (2026-10-13)."""
    sh = (ROOT / "installer" / "payload" / "install.sh").read_text()
    needed = re.search(r"pkgs=\(([^)]*)\)", sh).group(1).split()
    listed = set()
    for f in (LB / "config" / "package-lists").glob("*.list.chroot"):
        listed |= {ln.strip() for ln in f.read_text().splitlines()
                   if ln.strip() and not ln.startswith("#")}
    missing = [p for p in needed if p not in listed and p != "python3"]
    assert not missing, f"not on the stick: {missing}"


def test_owner_guide_explains_a_phone_as_the_network():
    doc = (ROOT / "docs" / "LIVE-USB.md").read_text()
    assert "USB tethering" in doc
