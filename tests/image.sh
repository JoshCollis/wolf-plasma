#!/usr/bin/env bash
set -euo pipefail
test -x /entrypoint.sh
for hook in 10-setup_user 15-setup_devices 30-nvidia; do
    test -f "/etc/cont-init.d/$hook.sh"
done
for cmd in startplasma-x11 kwin_x11 plasmashell plasma-discover systemsettings dolphin konsole kate ark \
    flatpak bwrap Xwayland xdpyinfo xrandr kwriteconfig6 kreadconfig6 clustercut \
    ncdu ping traceroute ssh git curl wget jq rg tmux nano less rsync dig ip ss ps lsof strace file diff patch \
    tar gzip xz zstd zip unzip 7z python3 pip3 node npm gcc g++ make cmake pkg-config gdb; do
    command -v "$cmd"
done
test "$(stat -c %a /usr/bin/bwrap)" = 755
test -f /usr/share/color-schemes/DraculaPurple.colors
test -f /usr/share/Kvantum/Dracula-purple/Dracula-purple.kvconfig
test -f /usr/share/themes/Dracula/gtk-3.0/gtk.css
test -f /usr/share/icons/Papirus-Dark/index.theme
python3 - <<'PY'
import json
from pathlib import Path
metadata = json.loads(Path('/usr/share/plasma/look-and-feel/Dracula/metadata.json').read_text())
assert metadata['KPlugin']['Id'] == 'Dracula'
assert not metadata.get('X-KPackage-Dependencies')
PY
for package in plasma-discover-packagekit sddm firefox chromium libreoffice-core; do
    if rpm -q "$package" >/dev/null 2>&1; then
        printf 'Unexpected desktop expansion: %s\n' "$package" >&2
        exit 1
    fi
done
python3 -m venv /tmp/wolf-plasma-test-venv
/tmp/wolf-plasma-test-venv/bin/python -m pip --version
test -z "$(flatpak remotes --system --columns=name)"
test -f /var/lib/flatpak/repo/config
grep -qx 'Command=/bin/bash' /opt/wolf-plasma/Dracula.profile
test -f /usr/share/aurorae/themes/Dracula/Dracularc
grep -qx 'library=org.kde.kwin.aurorae' /usr/share/plasma/look-and-feel/Dracula/contents/defaults
grep -qx 'theme=__aurorae__svg__Dracula' /usr/share/plasma/look-and-feel/Dracula/contents/defaults
rpm -q gnupg2 pinentry-qt kwalletmanager5 kleopatra
KDE_FULL_SESSION=true pinentry --version | grep -q '^pinentry-qt '
command -v kleopatra
test ! -d /home/retro/.gnupg/private-keys-v1.d
test "$(rpm -q --qf '%{VERSION}' cluster-cut)" = 0.4.4
desktop-file-validate /etc/xdg/autostart/ClusterCut.desktop
grep -qx 'Exec=env GDK_BACKEND=x11 WEBKIT_DISABLE_DMABUF_RENDERER=1 /usr/bin/clustercut --minimized' /etc/xdg/autostart/ClusterCut.desktop
desktop-file-validate /usr/share/applications/ClusterCut.desktop
grep -qx 'Exec=env GDK_BACKEND=x11 WEBKIT_DISABLE_DMABUF_RENDERER=1 /usr/bin/clustercut' /usr/share/applications/ClusterCut.desktop
test -s /usr/share/doc/wolf-plasma/clustercut/LICENSE
test -s /usr/share/doc/wolf-plasma/clustercut/source-v0.4.4.tar.gz
test ! -d /home/retro/.config/app.clustercut.clustercut
printf '%s\n' 'Image assertions passed'
