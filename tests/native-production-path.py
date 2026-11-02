#!/usr/bin/env python3
"""Actual image launcher wiring only: explicitly NOT native rendering acceptance."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def main():
    assert os.getuid() != 0
    env = dict(os.environ, LIBGL_ALWAYS_SOFTWARE='1', GAMESCOPE_WIDTH='800',
               GAMESCOPE_HEIGHT='600', GAMESCOPE_REFRESH='60')
    state = Path(env['HOME']) / '.local/state/wolf-plasma'
    state.mkdir(parents=True, exist_ok=True)
    (state / 'brave-v1').touch()
    parent = subprocess.Popen(['dbus-run-session', '--', '/usr/bin/kwin_wayland', '--virtual',
        '--socket', 'contract-parent', '--width', '800', '--height', '600'], env=env,
        start_new_session=True)
    desktop, info = None, None
    try:
        path = Path(env['XDG_RUNTIME_DIR']) / 'contract-parent'
        for _ in range(100):
            if path.is_socket():
                break
            assert parent.poll() is None
            time.sleep(.1)
        env['WOLF_PLASMA_PARENT_WAYLAND'] = str(path)
        desktop = subprocess.Popen(['/opt/gow/startup.sh'], env=env)
        for _ in range(200):
            files = list(Path(env['XDG_RUNTIME_DIR']).glob('wolf-plasma-*/compositor.json'))
            if files:
                break
            assert desktop.poll() is None, 'Actual native startup exited before launching KWin'
            time.sleep(.1)
        assert len(files) == 1, files
        info = json.loads(files[0].read_text())
        args = Path(f'/proc/{info["pid"]}/cmdline').read_bytes().decode().split('\0')
        assert args[0] == '/usr/bin/kwin_wayland', args
        assert args[args.index('--wayland-display') + 1] == str(path), args
        assert args[args.index('--width') + 1] == '800', args
        assert args[args.index('--height') + 1] == '600', args
        assert '--wayland-fd' in args and '--socket' in args, args
        assert not any(arg.startswith('--xwayland') for arg in args), args
        names = subprocess.check_output(['ps', '-e', '-o', 'comm='], text=True).splitlines()
        assert 'Xwayland' not in names and 'Xorg' not in names, names
        print('PASS: actual packaged native launcher chain, one nested compositor, '
              'original parent and geometry, no X11 launch; NOT compositing/pixel acceptance', flush=True)
    finally:
        if desktop and desktop.poll() is None:
            desktop.terminate()
            assert desktop.wait(timeout=20) != 0
        if info:
            for _ in range(50):
                if not Path(f'/proc/{info["pid"]}').exists():
                    break
                time.sleep(.1)
            assert not Path(f'/proc/{info["pid"]}').exists(), 'Nested KWin leaked after session stop'
        os.killpg(parent.pid, signal.SIGTERM) if parent.poll() is None else None
        parent.wait(timeout=10)


if __name__ == '__main__':
    main()
