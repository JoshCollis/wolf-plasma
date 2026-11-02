#!/usr/bin/env python3
"""Disposable native browser gate with the complete existing application policy."""
import os
from pathlib import Path
import sys

from production_policy import application_config, run_container

ROOT = Path(__file__).resolve().parents[1]
COMMAND = ('cp /tests/virtual-wrapper.sh /usr/local/bin/kwin_wayland_wrapper; '
           'chmod +x /usr/local/bin/kwin_wayland_wrapper; '
           'exec bash /tests/with-udmabuf.sh python3 /tests/native-headless.py')


def browser_config(image, volume, device_identity):
    return application_config(image, [COMMAND], network='none', cpus=3,
        binds=[f'{volume}:/home/retro', f'{ROOT / "tests"}:/tests:ro'],
        devices=['/dev/udmabuf'], env=[
            'GOW_REQUIRED_DEVICES=/dev/udmabuf',
            'WOLF_PLASMA_TEST_HOST_UDMABUF_ID=' + device_identity,
            'NATIVE_BROWSER_GATE=1', 'GAMESCOPE_REFRESH=60'])


if __name__ == '__main__':
    image, volume = sys.argv[1:]
    device = os.stat('/dev/udmabuf')
    raise SystemExit(run_container(browser_config(image, volume, f'{device.st_dev}:{device.st_ino}'), timeout=180))
