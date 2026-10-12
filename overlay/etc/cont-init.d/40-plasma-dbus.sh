#!/usr/bin/env bash
install -d -m 0755 /run/dbus
dbus-uuidgen --ensure=/etc/machine-id
if ! dbus-send --system --type=method_call --print-reply \
    --dest=org.freedesktop.DBus / org.freedesktop.DBus.ListNames >/dev/null 2>&1; then
    dbus-daemon --system --fork --nopidfile
fi
