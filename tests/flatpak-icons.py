#!/usr/bin/env python3
"""New Flatpak icon directories must become visible to an existing KDE client."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def check(home, catalogue_only=False):
    export = home / '.local/share/flatpak/exports/share'
    theme = export / 'icons/hicolor'
    (theme / '128x128/apps').mkdir(parents=True)
    (theme / 'index.theme').write_text(
        '[Icon Theme]\nName=Hicolor\nDirectories=128x128/apps,512x512/apps\n'
        '\n[128x128/apps]\nSize=128\nType=Fixed\nContext=Applications\n'
        '\n[512x512/apps]\nSize=512\nType=Fixed\nContext=Applications\n')
    config = home / '.config'
    config.mkdir()
    globals_file = config / 'kdeglobals'
    globals_file.write_text('[Icons]\nTheme=Papirus-Dark\n')
    original_config = globals_file.read_bytes()
    os.environ.update(HOME=str(home), XDG_CONFIG_HOME=str(config),
                      XDG_DATA_HOME=str(home / '.local/share'),
                      XDG_CACHE_HOME=str(home / '.cache'),
                      XDG_DATA_DIRS=str(export) + ':/usr/share',
                      QT_QPA_PLATFORM='offscreen', QT_NO_XDG_DESKTOP_PORTAL='1',
                      QT_QPA_PLATFORMTHEME='kde')
    from PySide6.QtGui import QGuiApplication, QIcon, QImage, QColor
    app = QGuiApplication([])
    name = 'org.wolfplasma.IconRegression'
    assert QIcon.fromTheme(name).isNull()
    (theme / '512x512/apps').mkdir(parents=True)
    image = QImage(512, 512, QImage.Format.Format_ARGB32)
    image.fill(QColor('#76b900'))
    asset = theme / '512x512/apps' / (name + '.png')
    assert image.save(str(asset))
    original_asset = asset.read_bytes()
    # Unknown names are retried after five seconds, but absent size directories
    # are not rediscovered by the long-lived KIconLoader on that retry.
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.05)
    assert QIcon.fromTheme(name).isNull(), 'Missing-directory regression not reproduced'
    print('RED reproduced: existing KDE client misses newly exported size directory', flush=True)
    applications = export / 'applications'
    applications.mkdir()
    (applications / (name + '.desktop')).write_text(
        f'[Desktop Entry]\nType=Application\nName=Icon regression\nExec=true\nIcon={name}\n')
    subprocess.run(['kbuildsycoca6', '--noincremental'] if catalogue_only else
                   ['wolf-plasma-refresh-apps'], check=True, timeout=35)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and QIcon.fromTheme(name).isNull():
        app.processEvents()
        time.sleep(.05)
    assert not QIcon.fromTheme(name).pixmap(48, 48).isNull(), 'Icon refresh did not reach existing client'
    assert QIcon.fromTheme(name).pixmap(48, 48).toImage().pixelColor(24, 24).name() == '#76b900'
    subprocess.run(['wolf-plasma-refresh-apps'], check=True, timeout=35)
    assert globals_file.read_bytes() == original_config
    assert asset.read_bytes() == original_asset
    assert list((home / '.cache').glob('ksycoca6_*')), 'Application catalogue not built'
    print('PASS: existing KDE client refreshed; repeat safe; theme and asset unchanged')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] != '--catalogue-only':
        check(Path(sys.argv[1]), '--catalogue-only' in sys.argv)
    else:
        # Never send the test's icon-refresh signal onto a real desktop bus.
        with tempfile.TemporaryDirectory(prefix='flatpak-icons-') as directory:
            home = Path(directory)
            runtime = home / 'runtime'
            runtime.mkdir(mode=0o700)
            subprocess.run(['dbus-run-session', '--', sys.executable, __file__, str(home), *sys.argv[1:]],
                           env={**os.environ, 'XDG_RUNTIME_DIR': str(runtime)},
                           check=True, timeout=50)
