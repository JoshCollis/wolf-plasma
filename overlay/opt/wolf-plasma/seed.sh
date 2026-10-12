#!/usr/bin/env bash
set -euo pipefail
config=${XDG_CONFIG_HOME:-$HOME/.config}
state=${XDG_STATE_HOME:-$HOME/.local/state}/wolf-plasma
mkdir -p "$config" "$state"
exec 9>"$state/seed.lock"
flock 9
# Required by this container's startup architecture even for an existing profile.
kwriteconfig6 --file startkderc --group General --key systemdBoot false
# Repair the shipped profile from older builds without replacing custom shells.
profile="$HOME/.local/share/konsole/Dracula.profile"
if [[ -f $profile && -z $(kreadconfig6 --file "$profile" --group General --key Command) ]]; then
    kwriteconfig6 --file "$profile" --group General --key Command /bin/bash
fi
[[ ! -e $state/defaults-v1 ]] || exit 0
fresh=false
[[ -e $config/kdeglobals ]] || fresh=true
# The classic startup requirement is a safe key update, not a home replacement.
if $fresh; then
    plasma-apply-lookandfeel --apply Dracula
    # Overrides explicitly follow global theme application.
    plasma-apply-colorscheme DraculaPurple
    kwriteconfig6 --file kdeglobals --group Icons --key Theme Papirus-Dark
    kwriteconfig6 --file kdeglobals --group KDE --key widgetStyle kvantum
    kwriteconfig6 --file kdeglobals --group General --key AccentColor '189,147,249'
    kwriteconfig6 --file kdeglobals --group General --key BrowserApplication com.brave.Browser.desktop
    kwriteconfig6 --file kcminputrc --group Mouse --key cursorTheme breeze_cursors
    kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key library org.kde.kwin.aurorae
    kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key theme __aurorae__svg__Dracula
    kwriteconfig6 --file kwinrc --group Compositing --key Enabled false
    kwriteconfig6 --file ksplashrc --group KSplash --key Engine none
    kwriteconfig6 --file kscreenlockerrc --group Daemon --key Autolock false
    kwriteconfig6 --file baloofilerc --group 'Basic Settings' --key 'Indexing-Enabled' false
    mkdir -p "$config/Kvantum" "$config/gtk-3.0" "$config/gtk-4.0" "$HOME/.local/share/konsole"
    printf '[General]\ntheme=Dracula-purple\n' > "$config/Kvantum/kvantum.kvconfig"
    printf '[Settings]\ngtk-theme-name=Dracula\ngtk-icon-theme-name=Papirus-Dark\ngtk-application-prefer-dark-theme=true\n' > "$config/gtk-3.0/settings.ini"
    printf '[Settings]\ngtk-application-prefer-dark-theme=true\n' > "$config/gtk-4.0/settings.ini"
    cp -n /opt/wolf-plasma/Dracula.* "$HOME/.local/share/konsole/"
    kwriteconfig6 --file konsolerc --group 'Desktop Entry' --key DefaultProfile Dracula.profile
    kwriteconfig6 --file konsolerc --group MainWindow --key MenuBar Disabled
    kwriteconfig6 --file konsolerc --group MainWindow --key ToolBarsMovable Disabled
    kwriteconfig6 --file konsolerc --group FileLocation --key scrollbackUseCacheLocation true
    kwriteconfig6 --file konsolerc --group FileLocation --key scrollbackUseSystemLocation false
    # Default browser association can be set before its exported desktop file exists.
    kwriteconfig6 --file mimeapps.list --group 'Default Applications' --key x-scheme-handler/http com.brave.Browser.desktop
    kwriteconfig6 --file mimeapps.list --group 'Default Applications' --key x-scheme-handler/https com.brave.Browser.desktop
    kwriteconfig6 --file mimeapps.list --group 'Default Applications' --key text/html com.brave.Browser.desktop
    if command -v gsettings >/dev/null; then
        gsettings set org.gnome.desktop.interface color-scheme prefer-dark
        gsettings set org.gnome.desktop.interface gtk-theme Dracula
    fi
    for dir in Desktop Documents Downloads Music Pictures Public Templates Videos; do
        mkdir -p "$HOME/$dir"
    done
fi
# Atomic completion marker: later launches preserve preferences/layouts and app data.
touch "$state/defaults-v1.tmp"
mv "$state/defaults-v1.tmp" "$state/defaults-v1"
