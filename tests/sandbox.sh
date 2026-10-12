#!/usr/bin/env bash
# Execute inside a disposable WolfPlasma-equivalent runner as desktop user.
set -euo pipefail
test "$(id -u)" != 0
test "$(stat -c %a /usr/bin/bwrap)" = 755
unshare -Ur true
unshare -Urmpf --mount-proc true
bwrap --unshare-user --unshare-pid --ro-bind / / --proc /proc --dev /dev true
flatpak info --user com.brave.Browser
# Offline DOM probe exercises Brave's nested sandbox without disabling it.
result=$(timeout 90 flatpak run --user com.brave.Browser --headless --disable-gpu \
    --dump-dom 'data:text/html,<title>wolf-plasma-sandbox-ok</title>')
[[ $result = *'<title>wolf-plasma-sandbox-ok</title>'* ]]
printf '%s\n' 'Nested namespaces and Brave sandbox DOM probe passed (not a GPU proof)'
