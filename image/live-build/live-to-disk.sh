#!/bin/sh
# Full stick: run by the installer (late_command) on the system it just copied from the
# live image. Removes only what the live stick itself added for its encrypted storage, so
# the installed laptop behaves like any BAU install:
#   * bau-live-init and its enable link (the live PRIVATE/LIMITED mode check)
#   * the live.conf drop-ins that keep BAU's services off until the stick is unlocked
#   * the My Jarvis setup window that offers to make encrypted storage on the stick
#   * the enable links of BAU's services: on a laptop they wait for install.sh, which
#     creates their keys and enables them (they would fail at every boot until then)
# BAU itself is then installed by /opt/bau-payload/install.sh as on any laptop.
#
#   sh live-to-disk.sh /target
set -eu

T=${1:?usage: live-to-disk.sh TARGET_ROOT}
[ -d "$T/etc/systemd/system" ] || { echo "live-to-disk: $T is not an installed system" >&2; exit 1; }
U="$T/etc/systemd/system"

rm -f "$U/bau-live-init.service" "$U"/*.wants/bau-live-init.service
for f in "$U"/*.service.d/live.conf; do
  [ -e "$f" ] || continue
  rm -f "$f"
  rmdir "$(dirname "$f")" 2>/dev/null || true
done
rm -f "$T/etc/xdg/autostart/my-jarvis-setup.desktop" \
  "$T/usr/share/applications/my-jarvis-setup.desktop" \
  "$T/usr/share/applications/bau-install-to-disk.desktop"
for u in bau-recover.service bau-ui.service bau-governor.timer bau-regwatch.timer; do
  rm -f "$U"/*.wants/"$u"
done
echo "live-to-disk: live-only startup removed"
