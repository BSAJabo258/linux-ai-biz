---
name: stick-change
description: Change the My Jarvis USB stick image safely (Debian packages, files baked into the image, services, kernel or driver settings, llama.cpp) and prove it before the owner flashes it. Use for anything under image/, installer/ or the package lists, and for "put it on the stick", "fix it on the stick", "rebuild the stick".
---

# Stick change

The owner boots this stick on real hardware: a bad change means a machine that does not
start, has no Wi-Fi, no sound or no model. Prove every change in the pinned build before
saying it is done.

## 1. Facts come from evidence

- A package name, version, driver option or firmware file comes from the stick's own image
  or an official Debian page, never from memory. To read the current image (when the built
  image is on hand):

  ```bash
  docker run --rm <stick image> sh -c 'dpkg -l <pkg>; modinfo <module> | grep parm'
  ```

- Hardware facts come from the owner's check report (`docs/LAPTOP-CHECK.md`) or the
  maker's page, with the link and date in a comment next to the change.
- llama.cpp is pinned (build and commit in `image/inside.sh`). Every `LLAMA_ARG_*` BAU sets
  must exist in that build (`tests/test_stick_health.py` checks it).

## 2. Where things go

- Packages: `image/live-build/config/package-lists/my-jarvis.list.chroot` and the same
  name in `installer/payload/install.sh`'s list (a test keeps them equal).
- Files on the stick: `image/live-build/config/includes.chroot/...` (same path as on the
  stick). Setup steps run in `image/live-build/config/hooks/live/0500-bau.hook.chroot`.
- Already-installed machines do not get a new stick's files: give the owner the one
  command to run there too (see `docs/DESKTOP.md`, "Already installed from an older
  stick?").

## 3. Test first, then prove it

1. A test in `tests/` that reads the image config and fails without the change (plant the
   bad case once, see it fail, remove it).
2. `bash scripts/check.sh` must say ALL PASS (shellcheck covers every script).
3. The PR checks do NOT build the stick (their `image` job is the Docker test drive). Build
   the stick itself: **Actions > build-live > Run workflow** on the branch, or
   `bash image/build-live.sh --out DIR` (see `docs/BUILD-ISO.md`; Docker, about 15 GB).
   That build is the proof a package exists.
4. Boot it when the change touches startup (a VM is fine for software, not for drivers).

## 4. Tell the owner plainly

- What changed on the stick.
- What was tested here (build, VM boot) and what only the real machine can show (Wi-Fi,
  sound, the graphics card).
- The command for machines already installed.
- Never "it works" before it ran on the owner's hardware: say "should work, not tested on
  your hardware yet".
