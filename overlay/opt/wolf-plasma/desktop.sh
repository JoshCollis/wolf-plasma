#!/usr/bin/env bash
set -euo pipefail
dbus-update-activation-environment DISPLAY XAUTHORITY XDG_RUNTIME_DIR XDG_DATA_DIRS \
    XDG_CURRENT_DESKTOP XDG_SESSION_TYPE XDG_SESSION_DESKTOP DESKTOP_SESSION \
    KDE_FULL_SESSION KDE_SESSION_VERSION HOME LANG
/opt/wolf-plasma/seed.sh
/opt/wolf-plasma/gpg-session.sh
# User remote/bootstrap is asynchronous: network failure must not block Plasma.
/usr/local/bin/wolf-plasma-brave --background &
exec startplasma-x11
