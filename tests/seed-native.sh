#!/usr/bin/env bash
# Real configuration-tool regressions, only in a disposable container/home.
set -euo pipefail
test "$(id -u)" != 0
export QT_QPA_PLATFORM=offscreen QT_NO_XDG_DESKTOP_PORTAL=1
mkdir -p "$HOME/.local/state/wolf-plasma" "$HOME/.config"
state="$HOME/.local/state/wolf-plasma"
touch "$state/defaults-v1"
kwriteconfig6 --file kdeglobals --group Icons --key Theme user-choice
kwriteconfig6 --file kwinrc --group Compositing --key Enabled false
kwriteconfig6 --file kwinrc --group Compositing --key UserSetting preserve-me
before=$(sha256sum "$HOME/.config/kdeglobals")
/opt/wolf-plasma/seed.sh
test -z "$(kreadconfig6 --file kwinrc --group Compositing --key Enabled)"
test "$(kreadconfig6 --file kwinrc --group Compositing --key UserSetting)" = preserve-me
test "$before" = "$(sha256sum "$HOME/.config/kdeglobals")"
# After the one-time migration, even a new explicit false is user-owned.
kwriteconfig6 --file kwinrc --group Compositing --key Enabled false
/opt/wolf-plasma/seed.sh
test "$(kreadconfig6 --file kwinrc --group Compositing --key Enabled)" = false
# A home never seeded by the image is not eligible for the old-default repair.
export XDG_STATE_HOME="$HOME/.local/state-unseeded"
mkdir -p "$XDG_STATE_HOME/wolf-plasma"
/opt/wolf-plasma/seed.sh
test "$(kreadconfig6 --file kwinrc --group Compositing --key Enabled)" = false
printf '%s\n' 'PASS: precise native seed migration, idempotence and user settings preserved'
