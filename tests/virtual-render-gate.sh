#!/usr/bin/env bash
# Minimal real-compositing precondition. Run as GoW user inside dbus-run-session.
set -euo pipefail
export LIBGL_ALWAYS_SOFTWARE=1 QT_QPA_PLATFORM=wayland
/usr/bin/kwin_wayland --virtual --socket virtual-gate --width 640 --height 480 &
pid=$!
trap 'kill -TERM "$pid" 2>/dev/null || true; wait "$pid" || true' EXIT
for _ in {1..50}; do
    kill -0 "$pid"
    state=$(dbus-send --session --type=method_call --print-reply --dest=org.kde.KWin \
        /Compositor org.freedesktop.DBus.Properties.Get \
        string:org.kde.kwin.Compositing string:active 2>/dev/null || true)
    if [[ $state = *'boolean true'* ]]; then
        printf '%s\n' 'PASS: virtual compositor active (not Wolf/GPU acceptance)'
        exit 0
    fi
    sleep .1
done
printf 'FAIL: virtual compositing never active. Last D-Bus reply: %s\n' "$state" >&2
printf '%s\n' 'KWin 6.8 requires a usable render device or /dev/udmabuf; no device/module/infrastructure changes are authorized here.' >&2
exit 1
