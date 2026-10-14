#!/usr/bin/env python3
"""Isolated real Sway/Xwayland mode + Present COPY probe (software, not Wolf).

Default gate proves parent/mode agreement and rejects a 60-parent/144-request.
--require-cadence also gates COPY and callback cadence within 5%; this is not
GPU/encoder/Moonlight acceptance. No profile or active socket is mounted.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import tempfile
import time

spec = importlib.util.spec_from_file_location('refresh', '/opt/wolf-plasma/refresh.py')
assert spec is not None and spec.loader is not None
refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--require-cadence', action='store_true')
parser.add_argument('--output', default='/home/retro/refresh-results.json')
args = parser.parse_args()
results = []
for parent_rate, request in [(rate, rate) for rate in (60, 90, 120, 144)] + [(60, 144)]:
    with tempfile.TemporaryDirectory(prefix='refresh-') as name:
        root = Path(name)
        runtime = root / 'runtime'; runtime.mkdir(mode=0o700)
        home = root / 'home'; home.mkdir(mode=0o700)
        config = root / 'sway.conf'
        config.write_text(f'output HEADLESS-1 mode --custom 640x480@{parent_rate}Hz\nxwayland disable\n')
        env = os.environ | {'HOME': str(home), 'XDG_RUNTIME_DIR': str(runtime),
                            'DISPLAY': ':87', 'WLR_BACKENDS': 'headless',
                            'WLR_LIBINPUT_NO_DEVICES': '1', 'WLR_RENDERER': 'pixman',
                            'LIBGL_ALWAYS_SOFTWARE': '1'}
        env.pop('WAYLAND_DISPLAY', None)
        env.pop('WOLF_PLASMA_PARENT_WAYLAND', None)
        with (root / 'sway.log').open('w') as log:
            sway = subprocess.Popen(['sway', '--unsupported-gpu', '-c', str(config)], env=env, stdout=log, stderr=log)
        x = None
        try:
            deadline = time.monotonic() + 10
            while True:
                sockets = list(runtime.glob('wayland-*'))
                sockets = [p for p in sockets if p.is_socket()]
                if sockets:
                    break
                if sway.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('Sway failed: ' + (root / 'sway.log').read_text())
                time.sleep(0.05)
            parent = str(sockets[0])
            while True:
                modes = refresh.parent_modes(parent)
                try:
                    refresh.require_parent_mode(modes, 640, 480, parent_rate)
                    break
                except RuntimeError:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(0.05)
            result = {'parent_Hz': parent_rate, 'requested_Hz': request, 'parent_modes': modes}
            if parent_rate != request:
                try:
                    refresh.require_parent_mode(modes, 640, 480, request)
                except RuntimeError as exc:
                    result.update(rejected=True, reason=str(exc))
                else:
                    raise AssertionError('Mismatched parent accepted')
            else:
                refresh.require_parent_mode(modes, 640, 480, request)
                auth = root / 'Xauthority'; auth.touch(mode=0o600)
                env.update(WAYLAND_DISPLAY=parent, XAUTHORITY=str(auth))
                subprocess.run(['xauth', '-f', str(auth), 'add', ':87', '.', os.urandom(16).hex()], check=True)
                with (root / 'xwayland.log').open('w') as log:
                    x = subprocess.Popen(['/usr/local/libexec/wolf-plasma/Xwayland', ':87', '-fullscreen', '-geometry', '640x480',
                                          '-fakescreenfps', str(request), '-nolisten', 'tcp', '-noreset', '-auth', str(auth)],
                                         env=env | {'WAYLAND_DEBUG': '1'}, stdout=log, stderr=log)
                deadline = time.monotonic() + 15
                while subprocess.run(['xdpyinfo'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
                    if x.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError('Xwayland failed: ' + (root / 'xwayland.log').read_text())
                    time.sleep(0.05)
                randr = subprocess.run(['xrandr', '--current'], env=env, capture_output=True, text=True, check=True).stdout
                current = next(line for line in randr.splitlines() if '*' in line)
                rate = float(re.search(r'([0-9.]+)\*', current)[1])
                assert abs(rate - request) < 1, randr
                present = subprocess.run(['/usr/local/libexec/wolf-plasma/present-probe'], env=env, capture_output=True, text=True, timeout=20, check=True)
                result.update(randr_Hz=rate, present=json.loads(present.stdout))
                debug = (root / 'xwayland.log').read_text()
                ids = set(re.findall(r'\.frame\(new id wl_callback(?:@|#)(\d+)\)', debug))
                stamps = [int(match[2]) for match in re.finditer(r'wl_callback(?:@|#)(\d+)\.done\((\d+)\)', debug) if match[1] in ids]
                diffs = [(b - a) % (2 ** 32) for a, b in zip(stamps, stamps[1:])]
                diffs = [diff for diff in diffs if 0 < diff < 100]
                result['callback_Hz'] = 1000 / statistics.mean(diffs) if diffs else None
                result['callback_samples'] = len(diffs)
                result['cadence_pass'] = bool(diffs and abs(result['callback_Hz'] / request - 1) <= 0.05 and abs(result['present']['copy_Hz'] / request - 1) <= 0.05)
            results.append(result)
            Path(args.output).write_text(json.dumps(results, indent=2) + '\n')
            print(json.dumps(result), flush=True)
        finally:
            if x is not None:
                x.terminate(); x.wait(timeout=5)
            sway.terminate(); sway.wait(timeout=5)
assert len(results) == 5 and results[-1]['rejected']
print('PASS: negotiated parent/mode matrix and mismatched-parent rejection; software cadence recorded separately', flush=True)
if args.require_cadence and not all(row['cadence_pass'] for row in results[:-1]):
    raise SystemExit('FAIL: software COPY/callback cadence outside 5%; not high-refresh acceptance')
