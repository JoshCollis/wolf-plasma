#!/usr/bin/env bash
# Real KDE tools and image theme defaults, in disposable homes only.
set -euo pipefail
test "$(id -u)" != 0
export QT_QPA_PLATFORM=offscreen QT_NO_XDG_DESKTOP_PORTAL=1
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT

use_home() {
    export HOME="$work/$1"
    export XDG_CONFIG_HOME="$HOME/.config" XDG_STATE_HOME="$HOME/.local/state"
    export XDG_DATA_HOME="$HOME/.local/share" XDG_CACHE_HOME="$HOME/.cache"
    mkdir -p "$XDG_CONFIG_HOME" "$XDG_STATE_HOME/wolf-plasma"
}

assert_layout() {
    test "$(kreadconfig6 --file kwinrc --group org.kde.kdecoration2 --key ButtonsOnLeft)" = XIA
    # A missing key also reads as empty without --default; require explicit empty.
    test -z "$(kreadconfig6 --file kwinrc --group org.kde.kdecoration2 --key ButtonsOnRight --default missing)"
    grep -qx 'ButtonsOnRight=' "$XDG_CONFIG_HOME/kwinrc"
    test -f "$XDG_STATE_HOME/wolf-plasma/decoration-buttons-v1"
}

assert_repeat() {
    local before
    before=$(sha256sum "$XDG_CONFIG_HOME/kwinrc" "$XDG_CONFIG_HOME/kdeglobals")
    /opt/wolf-plasma/seed.sh
    test "$before" = "$(sha256sum "$XDG_CONFIG_HOME/kwinrc" "$XDG_CONFIG_HOME/kdeglobals")"
}

use_home fresh
/opt/wolf-plasma/seed.sh
assert_layout
test "$(kreadconfig6 --file kwinrc --group org.kde.kdecoration2 --key library)" = org.kde.kwin.aurorae
test "$(kreadconfig6 --file kwinrc --group org.kde.kdecoration2 --key theme)" = __aurorae__svg__Dracula
test "$(kreadconfig6 --file kdeglobals --group Icons --key Theme)" = Papirus-Dark
assert_repeat

# Cover both previously image-seeded and pre-existing unseeded profiles.
for kind in seeded unseeded; do
    use_home "$kind"
    if [[ $kind = seeded ]]; then
        touch "$XDG_STATE_HOME/wolf-plasma/defaults-v1"
    fi
    # The reported live configuration has no explicit button keys.
    cat > "$XDG_CONFIG_HOME/kwinrc" <<'EOF'
[org.kde.kdecoration2]
library=org.kde.kwin.aurorae.v2
theme=__aurorae__svg__Dracula
BorderSize=Tiny

[Unrelated]
Keep=exactly this
EOF
    kwriteconfig6 --file kdeglobals --group Icons --key Theme custom-icons
    kwriteconfig6 --file kdeglobals --group General --key ColorScheme custom-colors
    before=$(sha256sum "$XDG_CONFIG_HOME/kdeglobals")
    cp "$XDG_CONFIG_HOME/kwinrc" "$work/expected-kwinrc"
    kwriteconfig6 --file "$work/expected-kwinrc" --group org.kde.kdecoration2 --key ButtonsOnLeft XIA
    kwriteconfig6 --file "$work/expected-kwinrc" --group org.kde.kdecoration2 --key ButtonsOnRight ''
    /opt/wolf-plasma/seed.sh
    assert_layout
    cmp "$work/expected-kwinrc" "$XDG_CONFIG_HOME/kwinrc"
    test "$before" = "$(sha256sum "$XDG_CONFIG_HOME/kdeglobals")"
    assert_repeat
    # After migration, both nonempty and explicitly empty user choices survive.
    kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key ButtonsOnLeft ''
    kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key ButtonsOnRight AIX
    assert_repeat
done
printf '%s\n' 'PASS: decoration defaults, one-time migration, explicit empty right and user preferences preserved'
