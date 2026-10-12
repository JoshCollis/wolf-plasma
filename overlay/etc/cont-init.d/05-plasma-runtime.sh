#!/usr/bin/env bash
# Sourced before GoW's user hook. Never chmod/chown the shared Wolf socket tree.
if [[ -n ${WAYLAND_DISPLAY:-} ]]; then
    if [[ $WAYLAND_DISPLAY = /* ]]; then
        export WOLF_PLASMA_PARENT_WAYLAND="$WAYLAND_DISPLAY"
    else
        export WOLF_PLASMA_PARENT_WAYLAND="${XDG_RUNTIME_DIR:?Wolf runtime directory required}/$WAYLAND_DISPLAY"
    fi
    # Wolf can mount a root-owned mode-0755 socket. Only this lobby's exact
    # socket needs desktop-user ownership; never recurse through its directory.
    if [[ ! -S $WOLF_PLASMA_PARENT_WAYLAND ]]; then
        printf 'Wolf parent Wayland socket missing: %s\n' "$WOLF_PLASMA_PARENT_WAYLAND" >&2
        exit 1
    fi
    chown -- "${PUID:-1000}:${PGID:-1000}" "$WOLF_PLASMA_PARENT_WAYLAND"
fi
# Xwayland/ICE cannot create their root-owned sticky directories after gosu.
install -d -m 1777 /tmp/.X11-unix /tmp/.ICE-unix
export XDG_RUNTIME_DIR="/run/user/${PUID:-1000}"
install -d -m 0700 -o "${PUID:-1000}" -g "${PGID:-1000}" "$XDG_RUNTIME_DIR"
