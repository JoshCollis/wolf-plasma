#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$DBUS_SESSION_BUS_ADDRESS" > "$WOLF_PLASMA_SESSION_STATE/bus"
dbus-update-activation-environment WAYLAND_DISPLAY XDG_RUNTIME_DIR XDG_DATA_DIRS \
    XDG_CURRENT_DESKTOP XDG_SESSION_TYPE XDG_SESSION_DESKTOP DESKTOP_SESSION \
    KDE_FULL_SESSION KDE_SESSION_VERSION HOME LANG
# Seed only configuration before KWin starts. Do not activate a GUI portal with
# the *parent* socket saved in its environment. User services start afterward.
QT_QPA_PLATFORM=offscreen QT_NO_XDG_DESKTOP_PORTAL=1 /opt/wolf-plasma/seed.sh
exec startplasma-wayland
