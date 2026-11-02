#!/usr/bin/env python3
"""Configure real KWin VirtualOutput custom modes; never production code."""
import json
import os
from pathlib import Path
import subprocess
import time

state = Path(os.environ['WOLF_PLASMA_SESSION_STATE'])
deadline = time.monotonic() + 40
while not (state / 'compositor.json').exists():
    if time.monotonic() >= deadline:
        raise SystemExit('Virtual compositor never started')
    time.sleep(.1)
info = json.loads((state / 'compositor.json').read_text())
env = dict(os.environ, WAYLAND_DISPLAY=info['socket'])
while time.monotonic() < deadline:
    result = subprocess.run(['kscreen-doctor', '-j'], env=env, capture_output=True, text=True)
    if result.returncode == 0:
        try:
            outputs = json.loads(result.stdout)['outputs']
            if outputs:
                break
        except (ValueError, KeyError):
            pass
    time.sleep(.1)
else:
    raise SystemExit('Virtual output configuration unavailable')
width, height, rate = [int(env[key]) for key in ('GAMESCOPE_WIDTH', 'GAMESCOPE_HEIGHT', 'GAMESCOPE_REFRESH')]
output = outputs[0]['name']
subprocess.run(['kscreen-doctor', f'output.{output}.addCustomMode.{width}.{height}.{rate * 1000}.reduced'],
               env=env, check=True, timeout=10)
subprocess.run(['kscreen-doctor', f'output.{output}.mode.{width}x{height}@{rate}'],
               env=env, check=True, timeout=10)
