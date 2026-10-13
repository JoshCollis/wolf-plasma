#!/usr/bin/env bash
# Run as the GoW user inside a disposable container, never on a persistent desktop.
set -euo pipefail
test "$(id -u)" != 0
expected_icons=Papirus-Dark
if [[ -e $HOME/.local/state/wolf-plasma/defaults-v1 ]]; then
    expected_icons=user-choice
    # Simulate the pre-fix profile: upgrading must repair only its missing command.
    kwriteconfig6 --file "$HOME/.local/share/konsole/Dracula.profile" --group General --key Command ""
    test "$(cat "$HOME/Documents/persistence.txt")" = persistent
fi
mkdir -p "$HOME/.local/state/wolf-plasma"
# Headless test deliberately stays offline. Brave namespace/network checks are separate.
touch "$HOME/.local/state/wolf-plasma/brave-v1"
printf 'output HEADLESS-1 resolution 1280x720\nxwayland disable\n' > /tmp/test-sway.conf
export WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 WLR_RENDERER=pixman LIBGL_ALWAYS_SOFTWARE=1
export GAMESCOPE_WIDTH=1280 GAMESCOPE_HEIGHT=720
sway --unsupported-gpu -c /tmp/test-sway.conf > /tmp/sway.log 2>&1 &
parent=$!
session=''
# Enable the actual keyboxd backend in this disposable persistent profile.
(umask 077; mkdir -p "$HOME/.gnupg"; printf 'use-keyboxd\n' > "$HOME/.gnupg/common.conf")
cleanup() {
    if [[ -n $session ]]; then kill -TERM "$session" 2>/dev/null || true; wait "$session" 2>/dev/null || true; fi
    kill -TERM "$parent" 2>/dev/null || true
    wait "$parent" 2>/dev/null || true
}
trap cleanup EXIT
for ((i=0; i<100; i++)); do
    for socket in "$XDG_RUNTIME_DIR"/wayland-*; do
        if [[ -S $socket ]]; then export WOLF_PLASMA_PARENT_WAYLAND="$socket"; break 2; fi
    done
    kill -0 "$parent" || { cat /tmp/sway.log; exit 1; }
    sleep 0.1
done
: "${WOLF_PLASMA_PARENT_WAYLAND:?Headless Wayland parent timed out}"
/opt/gow/startup.sh > /tmp/plasma.log 2>&1 &
session=$!
export DISPLAY=:0 XAUTHORITY="$XDG_RUNTIME_DIR/Xauthority"
for ((i=0; i<300; i++)); do
    kill -0 "$session" || { cat /tmp/plasma.log; exit 1; }
    if pgrep -u "$(id -u)" -x plasmashell >/dev/null && \
        xprop -root _NET_SUPPORTING_WM_CHECK 2>/dev/null | grep -q 'window id'; then break; fi
    sleep 0.1
done
pgrep -u "$(id -u)" -x plasmashell >/dev/null || { cat /tmp/plasma.log; exit 1; }
pgrep -u "$(id -u)" -x kwin_x11 >/dev/null
# Native ClusterCut must autostart on the same X11 desktop, including recreation.
for ((i=0; i<300; i++)); do
    if pgrep -u "$(id -u)" -x clustercut >/dev/null && ss -lun | grep -q ':4654 '; then break; fi
    sleep 0.1
done
pid=$(pgrep -u "$(id -u)" -x clustercut)
ss -lun | grep ':4654 '
tr '\0' '\n' < "/proc/$pid/environ" | grep '^GDK_BACKEND=x11$'
tr '\0' '\n' < "/proc/$pid/environ" | grep '^WEBKIT_DISABLE_DMABUF_RENDERER=1$'
tr '\0' '\n' < "/proc/$pid/environ" | grep '^XDG_SESSION_TYPE=x11$'
if tr '\0' '\n' < "/proc/$pid/environ" | grep -q '^WAYLAND_DISPLAY='; then exit 1; fi
for ((i=0; i<100; i++)); do
    if grep -q 'X11 clipboard change listener started (XFixes)' /tmp/ClusterCutLogs/clustercut.log.* 2>/dev/null; then break; fi
    sleep 0.1
done
grep -q 'X11 session detected, using tauri-plugin-clipboard backend' /tmp/ClusterCutLogs/clustercut.log.*
grep -q 'X11 clipboard change listener started (XFixes)' /tmp/ClusterCutLogs/clustercut.log.*
ss -ltn | grep ':4654 '
# The image must not share identities, and recreation must retain this profile's.
identity="$HOME/.config/app.clustercut.clustercut/device_id"
test -s "$identity"
if [[ -f $HOME/.local/state/wolf-plasma/test-clustercut-identity ]]; then
    cmp "$identity" "$HOME/.local/state/wolf-plasma/test-clustercut-identity"
else
    cp "$identity" "$HOME/.local/state/wolf-plasma/test-clustercut-identity"
fi
test "$(kreadconfig6 --file startkderc --group General --key systemdBoot)" = false
test "$(kreadconfig6 --file "$HOME/.local/share/konsole/Dracula.profile" --group General --key Command)" = /bin/bash
# Plasma 6.7 canonicalises the legacy Aurorae ID to the installed .v2 plugin.
[[ $(kreadconfig6 --file kwinrc --group org.kde.kdecoration2 --key library) =~ ^org\.kde\.kwin\.aurorae(\.v2)?$ ]]
test "$(kreadconfig6 --file kwinrc --group org.kde.kdecoration2 --key theme)" = __aurorae__svg__Dracula
test "$(kreadconfig6 --file kdeglobals --group Icons --key Theme)" = "$expected_icons"
display_info=$(xdpyinfo)
grep 'dimensions:' <<< "$display_info"
grep -q '1280x720 pixels' <<< "$display_info"
python3 /tests/gnupg.py
gpg --batch --list-keys
test -f "$HOME/.gnupg/public-keys.d/pubring.db.lock"
# Subsequent seed must preserve customizations and data, without another global-theme apply.
kwriteconfig6 --file kdeglobals --group Icons --key Theme user-choice
printf 'persistent\n' > "$HOME/Documents/persistence.txt"
before=$(sha256sum "$HOME/.config/kdeglobals")
dbus-run-session -- /opt/wolf-plasma/seed.sh
test "$before" = "$(sha256sum "$HOME/.config/kdeglobals")"
test -s "$HOME/Documents/persistence.txt"
# Session services inherit X11 and its one bus, never the parent Wayland socket.
pid=$(pgrep -u "$(id -u)" -x plasmashell)
tr '\0' '\n' < "/proc/$pid/environ" | grep '^XDG_SESSION_TYPE=x11$'
if tr '\0' '\n' < "/proc/$pid/environ" | grep -q '^WAYLAND_DISPLAY='; then exit 1; fi
if [[ ${FAILURE_TEST:-} = xwayland ]]; then
    pkill -TERM -u "$(id -u)" -x Xwayland
else
    kill -TERM "$session"
fi
set +e
for ((i=0; i<150; i++)); do
    kill -0 "$session" 2>/dev/null || break
    sleep 0.1
done
if kill -0 "$session" 2>/dev/null; then
    printf '%s\n' 'Session teardown exceeded 15 seconds' >&2
    exit 1
fi
wait "$session"
rc=$?
set -e
session=''
if [[ ${FAILURE_TEST:-} = xwayland ]]; then
    if [[ $rc == 0 ]]; then
        printf '%s\n' 'Session incorrectly reported success after Xwayland was killed'
        cat /tmp/plasma.log
        exit 1
    fi
else
    test "$rc" = 143
fi
! pgrep -u "$(id -u)" -x Xwayland
! pgrep -u "$(id -u)" -x plasmashell
! pgrep -u "$(id -u)" -x clustercut
! pgrep -u "$(id -u)" -x gpg-agent
! pgrep -u "$(id -u)" -x keyboxd
test ! -e "$HOME/.gnupg/public-keys.d/pubring.db.lock"
printf '%s\n' 'Headless Plasma startup, defaults, idempotence, environment and teardown passed'
