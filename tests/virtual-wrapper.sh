#!/usr/bin/env bash
# TEST ONLY: replace the nested backend, not Plasma, services or supervision.
# This file is bind-mounted over the image-local wrapper only in CPU tests.
set -euo pipefail
python3 /tests/virtual-mode.py &
exec /usr/bin/kwin_wayland_wrapper --virtual \
    --width "$GAMESCOPE_WIDTH" --height "$GAMESCOPE_HEIGHT"
