#!/usr/bin/env python3
"""CPU-only native desktop acceptance; KWin virtual != Wolf/GPU acceptance."""
import json
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, '/opt/wolf-plasma')
from refresh import parent_modes, require_parent_mode
from native_audio import AudioFixture


def run(args, **kwargs):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=15, **kwargs)


def main():
    assert os.getuid() != 0
    assert Path('/dev/udmabuf').exists() or list(Path('/dev/dri').glob('renderD*')), (
        'KWin 6.8 virtual compositing needs a real render device or /dev/udmabuf; '
        'this fixture has neither. Native UI/pixel/GPG acceptance is BLOCKED, not skipped. '
        'Do not treat socket/window mapping without active compositing as success.')
    env = dict(os.environ, LIBGL_ALWAYS_SOFTWARE='1', QT_QPA_PLATFORM='wayland')
    state = Path(os.environ['HOME']) / '.local/state/wolf-plasma'
    state.mkdir(parents=True, exist_ok=True)
    (state / 'brave-v1').touch()  # Offline tests do not download a browser.
    gpg_home = Path(env['HOME']) / '.gnupg'
    gpg_home.mkdir(mode=0o700, exist_ok=True)
    common = gpg_home / 'common.conf'
    if not common.exists():
        common.write_text('use-keyboxd\n')
    width, height, rate = 800, 600, int(os.environ.get('GAMESCOPE_REFRESH', '60'))
    env.update(GAMESCOPE_WIDTH=str(width), GAMESCOPE_HEIGHT=str(height), GAMESCOPE_REFRESH=str(rate))
    audio = AudioFixture(env)
    env = audio.start()
    # The synthetic parent is not the persistent desktop. Keep its KWin output
    # history separate so a previous desktop rate cannot relabel the fixture.
    parent_home = tempfile.TemporaryDirectory(prefix='test-parent-home-', dir=env['XDG_RUNTIME_DIR'])
    parent_launch_env = env | {'HOME': parent_home.name,
        'XDG_CONFIG_HOME': parent_home.name + '/.config',
        'XDG_STATE_HOME': parent_home.name + '/.local/state',
        'XDG_DATA_HOME': parent_home.name + '/.local/share'}
    parent_log = open('/tmp/native-parent.log', 'w+')
    parent = subprocess.Popen(['dbus-run-session', '--', '/usr/bin/kwin_wayland', '--virtual',
                               '--socket', 'cpu-parent', '--width', str(width), '--height', str(height)],
                               env=parent_launch_env, stdout=parent_log, stderr=subprocess.STDOUT, start_new_session=True)
    desktop = None
    plasma_log = open('/tmp/native-plasma.log', 'w+')
    try:
        path = str(Path(env['XDG_RUNTIME_DIR']) / 'cpu-parent')
        for _ in range(100):
            assert parent.poll() is None, 'Virtual parent exited'
            try:
                require_parent_mode(parent_modes(path), width, height, 60)
                break
            except (OSError, RuntimeError):
                time.sleep(.1)
        else:
            raise AssertionError('Virtual parent output never became ready')
        # At non-60 rates, configure the real parent via its private bus, obtained
        # from /proc of the compositor; this is synthetic test-owned state only.
        parent_pid = int(run(['pgrep', '-n', '-x', 'kwin_wayland']).strip())
        parent_env = dict(item.split('=', 1) for item in Path(f'/proc/{parent_pid}/environ').read_text().split('\0') if '=' in item)
        parent_env.update(WAYLAND_DISPLAY='cpu-parent', QT_QPA_PLATFORM='wayland')
        output = json.loads(run(['kscreen-doctor', '-j'], env=parent_env))['outputs'][0]['name']
        if rate != 60:
            run(['kscreen-doctor', f'output.{output}.addCustomMode.{width}.{height}.{rate * 1000}.reduced'], env=parent_env)
            run(['kscreen-doctor', f'output.{output}.mode.{width}x{height}@{rate}'], env=parent_env)
        require_parent_mode(parent_modes(path), width, height, rate)
        env['WOLF_PLASMA_PARENT_WAYLAND'] = path
        desktop = subprocess.Popen(['/opt/gow/startup.sh'], env=env, stdout=plasma_log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        for attempt in range(450):
            assert desktop.poll() is None, f'Native session exited {desktop.returncode}'
            plasma_log.seek(0)
            if 'Native Plasma ready:' in plasma_log.read():
                break
            if attempt == 100:
                for file in Path(env['XDG_RUNTIME_DIR']).glob('wolf-plasma-*/compositor.json'):
                    client = json.loads(file.read_text())
                    print('Readiness output:', parent_modes(str(Path(env['XDG_RUNTIME_DIR']) / client['socket'])), flush=True)
                    debug_env = env | {'DBUS_SESSION_BUS_ADDRESS': (file.parent / 'bus').read_text().strip()}
                    result = subprocess.run(['dbus-send', '--session', '--type=method_call', '--print-reply',
                        '--dest=org.kde.KWin', '/Compositor', 'org.freedesktop.DBus.Properties.Get',
                        'string:org.kde.kwin.Compositing', 'string:active'], env=debug_env,
                        capture_output=True, text=True, timeout=3)
                    print('Readiness D-Bus:', result.returncode, result.stdout, result.stderr, flush=True)
            time.sleep(.2)
        else:
            raise AssertionError('Native session readiness timeout')
        states = sorted(Path(env['XDG_RUNTIME_DIR']).glob('wolf-plasma-*/compositor.json'))
        assert len(states) == 1, states
        info = json.loads(states[0].read_text())
        env.update(WAYLAND_DISPLAY=info['socket'], DBUS_SESSION_BUS_ADDRESS=(states[0].parent / 'bus').read_text().strip())
        require_parent_mode(parent_modes(str(Path(env['XDG_RUNTIME_DIR']) / info['socket'])), width, height, rate)
        plasma_pid = int(run(['pgrep', '-x', 'plasmashell']).strip())
        client_env = dict(item.split('=', 1) for item in Path(f'/proc/{plasma_pid}/environ').read_text().split('\0') if '=' in item)
        assert client_env['WAYLAND_DISPLAY'] == info['socket'], client_env.get('WAYLAND_DISPLAY')
        assert client_env['XDG_SESSION_TYPE'] == 'wayland'
        assert not client_env.get('DISPLAY')
        assert client_env['QT_QPA_PLATFORM'] == 'wayland'
        assert client_env['GDK_BACKEND'] == 'wayland'
        expected_icons = 'user-choice' if (state / 'native-home-test-v1').exists() else 'Papirus-Dark'
        icons = ['kreadconfig6', '--file', 'kdeglobals', '--group', 'Icons', '--key', 'Theme']
        assert run(icons, env=client_env).strip() == expected_icons
        assert run(['kreadconfig6', '--file', 'startkderc', '--group', 'General', '--key', 'systemdBoot'], env=client_env).strip() == 'false'
        if (state / 'native-home-test-v1').exists():
            assert (Path(env['HOME']) / 'Documents/persistence.txt').read_text() == 'native-persistent\n'
        assert 'Xwayland' not in run(['ps', '-e', '-o', 'comm='])
        assert 'Xorg' not in run(['ps', '-e', '-o', 'comm='])
        subprocess.run(['python3', '/tests/native-ui.py'], env=client_env, check=True, timeout=90)
        run(['gpg', '--batch', '--list-keys'], env=client_env)
        assert (gpg_home / 'public-keys.d/pubring.db.lock').exists(), 'Real default keyboxd was not exercised'
        run(['kwriteconfig6', '--file', 'kdeglobals', '--group', 'Icons', '--key', 'Theme', 'user-choice'], env=client_env)
        globals_file = Path(client_env.get('XDG_CONFIG_HOME', str(Path(env['HOME']) / '.config'))) / 'kdeglobals'
        before = hashlib.sha256(globals_file.read_bytes()).hexdigest()
        run(['/opt/wolf-plasma/seed.sh'], env=client_env)
        assert hashlib.sha256(globals_file.read_bytes()).hexdigest() == before
        (Path(env['HOME']) / 'Documents/persistence.txt').write_text('native-persistent\n')
        (state / 'native-home-test-v1').touch()
        failure = os.environ.get('FAILURE_TEST', '')
        normal_logout = os.environ.get('EXIT_TEST') == 'logout'
        probe_stall = os.environ.get('EXIT_TEST') == 'probe-stall'
        if probe_stall:
            # Pause only this synthetic desktop's actual compositor. A health
            # request must hit its two-second timeout, then recover after CONT.
            os.kill(info['pid'], signal.SIGSTOP)
            try:
                time.sleep(4)
            finally:
                try:
                    os.kill(info['pid'], signal.SIGCONT)
                except ProcessLookupError:
                    pass
            time.sleep(2)
            assert desktop.poll() is None, 'One stalled IPC probe destroyed a live desktop'
            subprocess.run(['python3', '/tests/native-ui.py'], env=client_env, check=True, timeout=90)
            print('PASS: real KWin four-second stall, IPC timeout and recovered native UI/audio/GPG', flush=True)
        shutdown_deadline = time.monotonic() + 20
        if normal_logout:
            run(['gdbus', 'call', '--session', '--dest', 'org.kde.Shutdown',
                 '--object-path', '/Shutdown', '--method', 'org.kde.Shutdown.logout'], env=client_env)
        elif failure == 'compositor':
            os.kill(info['pid'], signal.SIGKILL)
        elif failure == 'parent':
            os.killpg(parent.pid, signal.SIGTERM)
        elif failure == 'mode':
            run(['kscreen-doctor', f'output.{output}.mode.800x600@60'], env=parent_env)
        else:
            desktop.terminate()
        status = desktop.wait(timeout=15)
        expected_status = 0 if normal_logout else 143
        assert status != 0 if failure else status == expected_status, status
        # The parent is deliberately still alive except in the parent-loss case.
        for name in ('plasmashell', 'gpg-agent', 'keyboxd', 'clustercut'):
            while True:
                found = subprocess.run(['pgrep', '-u', str(os.getuid()), '-x', name], capture_output=True, text=True)
                if found.returncode != 0 or time.monotonic() >= shutdown_deadline:
                    break
                time.sleep(.05)
            if found.returncode == 0:
                print(run(['ps', '-u', str(os.getuid()), '-o', 'pid,ppid,pgid,sid,stat,args']), flush=True)
            assert found.returncode != 0, f'{name} leaked: {found.stdout}'
        assert not (gpg_home / 'public-keys.d/pubring.db.lock').exists(), 'Keyboxd lock survived clean shutdown'
        outcome = 'logout' if normal_logout else 'probe-stall' if probe_stall else failure or 'signal'
        print(f'PASS: CPU virtual native desktop {width}x{height}@{rate}; teardown={outcome}', flush=True)
    finally:
        if desktop and desktop.poll() is None:
            desktop.terminate()
            desktop.wait(timeout=20)
        os.killpg(parent.pid, signal.SIGTERM) if parent.poll() is None else None
        parent.wait(timeout=10)
        parent_home.cleanup()
        audio.close()
        for log in (parent_log, plasma_log):
            log.seek(0)
            print(log.read())
            log.close()


if __name__ == '__main__':
    main()
