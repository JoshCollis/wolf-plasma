#!/usr/bin/env python3
"""Real isolated parent + patched rootful Xwayland mode tests (not FPS proof)."""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, '/opt/wolf-plasma')
from refresh import parent_modes, require_parent_mode

assert os.getuid() != 0
with tempfile.TemporaryDirectory(prefix='refresh-') as name:
    root = Path(name)
    for width, height in ((1920, 1200), (1912, 1192)):
        for rate in (60, 90, 120, 144):
            runtime = root / f'{width}-{rate}'
            runtime.mkdir(mode=0o700)
            config = runtime / 'sway.conf'
            config.write_text(f'output HEADLESS-1 mode --custom {width}x{height}@{rate}Hz\nxwayland disable\n')
            env = os.environ | {'XDG_RUNTIME_DIR': str(runtime), 'WLR_BACKENDS': 'headless',
                                'WLR_LIBINPUT_NO_DEVICES': '1', 'WLR_RENDERER': 'pixman',
                                'LIBGL_ALWAYS_SOFTWARE': '1', 'DISPLAY': ':89'}
            with (runtime / 'sway.log').open('w') as log:
                parent = subprocess.Popen(['sway', '--unsupported-gpu', '-c', str(config)], env=env, stdout=log, stderr=log)
                x = None
                try:
                    deadline = time.monotonic() + 10
                    sockets = []
                    while not sockets:
                        sockets = [p for p in runtime.glob('wayland-*') if p.is_socket()]
                        if parent.poll() is not None or time.monotonic() > deadline:
                            raise RuntimeError((runtime / 'sway.log').read_text())
                        time.sleep(.1)
                    path = str(sockets[0])
                    # Wait for the compositor config to set its custom headless mode.
                    while True:
                        modes = parent_modes(path)
                        try:
                            require_parent_mode(modes, width, height, rate)
                            break
                        except RuntimeError:
                            if time.monotonic() > deadline:
                                raise
                            time.sleep(.1)
                    auth = runtime / 'Xauthority'
                    auth.touch(mode=0o600)
                    env['XAUTHORITY'] = str(auth)
                    subprocess.run(['xauth', '-f', str(auth), 'add', ':89', '.', os.urandom(16).hex()], check=True)
                    with (runtime / 'xwayland.log').open('w') as xlog:
                        x = subprocess.Popen(['/usr/local/libexec/wolf-plasma/Xwayland', ':89', '-fullscreen',
                                              '-geometry', f'{width}x{height}', '-fakescreenfps', str(rate),
                                              '-nolisten', 'tcp', '-noreset', '-auth', str(auth)],
                                             env=env | {'WAYLAND_DISPLAY': path}, stdout=xlog, stderr=xlog)
                        deadline = time.monotonic() + 10
                        while subprocess.run(['xdpyinfo'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
                            if x.poll() is not None or time.monotonic() > deadline:
                                raise RuntimeError((runtime / 'xwayland.log').read_text())
                            time.sleep(.1)
                        randr = subprocess.run(['xrandr', '--current'], env=env, capture_output=True, text=True, check=True).stdout
                        current = next(line for line in randr.splitlines() if '*' in line)
                        actual = float(re.search(r'([0-9.]+)\*', current)[1])
                        assert current.split()[0] == f'{width}x{height}', randr
                        assert abs(actual - rate) < 1, randr
                        print(f'PASS parent={rate}Hz X11={actual}Hz geometry={width}x{height}', flush=True)
                        if rate == 60:
                            try:
                                require_parent_mode(modes, width, height, 144)
                            except RuntimeError:
                                print('PASS negative control: 144 request / 60 parent refused', flush=True)
                            else:
                                raise AssertionError('Mismatched rate accepted')
                finally:
                    if x is not None:
                        x.terminate(); x.wait(timeout=5)
                    parent.terminate(); parent.wait(timeout=5)
print('Mode and startup-contract acceptance only; Wolf/Moonlight frame cadence is not certified.')
