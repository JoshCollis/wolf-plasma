#!/usr/bin/env python3
"""Parent-run full native session against a NEW pinned-Wolf hardware fixture.

No virtual child override, software renderer, X11, real home or live Wolf API.
The host driver independently verifies pixels captured only by its Wolf fixture.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from native_audio import AudioFixture
from native_tools import script
from gi.repository import GLib

sys.path.insert(0, '/opt/wolf-plasma')
from refresh import parent_modes, require_parent_mode


def run(args, env, data=None):
    return subprocess.check_output(args, env=env, input=data, text=True,
                                   stderr=subprocess.STDOUT, timeout=20)


def event(name, **data):
    print(json.dumps({'event': name, **data}), flush=True)


def client_environment(state, env, info):
    result = env | {'WAYLAND_DISPLAY': info['socket'],
                    'DBUS_SESSION_BUS_ADDRESS': (state / 'bus').read_text().strip(),
                    'QT_QPA_PLATFORM': 'wayland', 'GDK_BACKEND': 'wayland',
                    'XDG_SESSION_TYPE': 'wayland', 'XDG_CURRENT_DESKTOP': 'KDE'}
    result.pop('DISPLAY', None)
    result.pop('XAUTHORITY', None)
    return result


def gpg_roundtrip(env, home):
    fingerprint = home / 'lab-fingerprint'
    if not fingerprint.exists():
        base = ['gpg', '--batch', '--pinentry-mode', 'loopback', '--passphrase', '']
        run(base + ['--quick-generate-key', 'GPU lab <lab@example.invalid>', 'ed25519', 'sign', '1d'], env)
        keys = run(['gpg', '--with-colons', '--list-secret-keys'], env)
        fpr = next(line.split(':')[9] for line in keys.splitlines() if line.startswith('fpr:'))
        run(base + ['--quick-add-key', fpr, 'cv25519', 'encr', '1d'], env)
        fingerprint.write_text(fpr)
    message = home / 'lab-message.gpg'
    run(['gpg', '--batch', '--yes', '--trust-model', 'always', '-r', fingerprint.read_text(),
         '-o', str(message), '--encrypt'], env, 'native-gpu-lab-roundtrip\n')
    assert run(['gpg', '--batch', '--pinentry-mode', 'loopback', '--passphrase', '',
                '--decrypt', str(message)], env).endswith('native-gpu-lab-roundtrip\n')
    protected = [home / 'common.conf', home / 'gpg-agent.conf', *sorted((home / 'private-keys-v1.d').glob('*'))]
    hashes = {str(path.relative_to(home)): hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
    manifest = home / 'lab-protected-sha256.json'
    if manifest.exists():
        assert json.loads(manifest.read_text()) == hashes, 'GPG key/config bytes changed across recreation'
    else:
        manifest.write_text(json.dumps(hashes))
    event('GPU_GPG_HASH_ROUNDTRIP_PASS')


def main():
    assert os.getuid() != 0
    env = dict(os.environ)
    assert env.get('LIBGL_ALWAYS_SOFTWARE') not in ('1', 'true')
    width, height, rate = [int(env[key]) for key in ('GAMESCOPE_WIDTH', 'GAMESCOPE_HEIGHT', 'GAMESCOPE_REFRESH')]
    assert (width, height) == (800, 600), 'This bounded application fixture is fixed at 800x600'
    parent = env['WOLF_PLASMA_PARENT_WAYLAND']
    case = env.get('GPU_GATE_CASE', 'session')
    actual_parent_rate = int(env.get('GPU_GATE_PARENT_RATE', str(rate)))
    require_parent_mode(parent_modes(parent), width, height, actual_parent_rate)
    home = Path(env['HOME'])
    state_home = home / '.local/state/wolf-plasma'
    state_home.mkdir(parents=True, exist_ok=True)
    (state_home / 'brave-v1').touch()  # Offline lab; the real WebKit sandbox is tested.
    gpg_home = Path(env.get('GNUPGHOME') or str(home / '.gnupg'))
    gpg_home.mkdir(mode=0o700, parents=True, exist_ok=True)
    for path, value in ((gpg_home / 'common.conf', 'use-keyboxd\n'),
                        (gpg_home / 'gpg-agent.conf', 'default-cache-ttl 90\n# GPU lab user configuration\n')):
        if not path.exists():
            path.write_text(value)
    audio = AudioFixture(env)
    desktop, marker = None, None
    log = open('/tmp/gpu-plasma.log', 'w+')
    try:
        env = audio.start()
        desktop = subprocess.Popen(['/opt/gow/startup.sh'], env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        if case == 'mismatch':
            status = desktop.wait(timeout=20)
            log.seek(0)
            assert status != 0 and 'Wolf parent/request mismatch' in log.read()
            event('GPU_GATE_RESULT', passed=True, case=case, parent_rate=actual_parent_rate, requested_rate=rate)
            return
        deadline = time.monotonic() + 65
        info, state, client = None, None, None
        next_observation = 0
        while time.monotonic() < deadline:
            assert desktop.poll() is None, f'Native desktop exited during warmup: {desktop.returncode}'
            states = list(Path(env['XDG_RUNTIME_DIR']).glob('wolf-plasma-*/compositor.json'))
            if states and (states[0].parent / 'bus').exists() and marker is None:
                assert len(states) == 1
                state = states[0].parent
                info = json.loads(states[0].read_text())
                args = Path(f'/proc/{info["pid"]}/cmdline').read_bytes().decode().split('\0')
                assert '--wayland-display' in args and '--virtual' not in args, args
                assert not any(arg.startswith('--xwayland') for arg in args), args
                client = client_environment(state, env, info)
                os.environ.update(client)
                # Drive actual presentation BEFORE demanding learned refresh.
                marker = subprocess.Popen(['python3', '/tests/native-ui.py', '--gtk'], env=client)
                event('GPU_MARKER_RUNNING', compositor_pid=info['pid'], requested_rate=rate)
            if client:
                try:
                    script(f'const w=workspace.windowList().find(w=>w.pid==={marker.pid}); '
                           'if(w){w.minimized=false;w.keepAbove=true;workspace.activeWindow=w;} return !!w;')
                except (GLib.Error, AssertionError):
                    # A startup D-Bus/script service may not yet exist; readiness
                    # below still requires the real negotiated output and pixels.
                    pass
                if time.monotonic() >= next_observation:
                    try:
                        modes = parent_modes(str(Path(env['XDG_RUNTIME_DIR']) / info['socket']))
                        active = run(['dbus-send', '--session', '--type=method_call', '--print-reply',
                            '--dest=org.kde.KWin', '/Compositor', 'org.freedesktop.DBus.Properties.Get',
                            'string:org.kde.kwin.Compositing', 'string:active'], client)
                        event('GPU_MODE_OBSERVATION', modes=modes, compositing_active='boolean true' in active)
                    except (OSError, RuntimeError, subprocess.SubprocessError):
                        pass  # Observation during startup is not the acceptance gate.
                    next_observation = time.monotonic() + 2
            log.seek(0)
            if f'Native Plasma ready: {width}x{height}@{rate}Hz' in log.read():
                break
            time.sleep(.2)
        else:
            modes = parent_modes(str(Path(env['XDG_RUNTIME_DIR']) / info['socket'])) if info else []
            raise AssertionError(f'Native refresh/readiness failed after actual marker warmup: {modes}')
        require_parent_mode(parent_modes(str(Path(env['XDG_RUNTIME_DIR']) / info['socket'])), width, height, rate)
        event('GPU_WARMED_MODE_PASS', modes=parent_modes(str(Path(env['XDG_RUNTIME_DIR']) / info['socket'])))
        time.sleep(5)  # Let the independent 2-Hz Wolf capture branch retain a full marker frame.
        marker.terminate()
        marker.wait(timeout=5)
        marker = None
        plasma_pid = int(run(['pgrep', '-x', 'plasmashell'], client).strip())
        actual = dict(item.split('=', 1) for item in Path(f'/proc/{plasma_pid}/environ').read_text().split('\0') if '=' in item)
        assert actual['WAYLAND_DISPLAY'] == info['socket'] and actual['XDG_SESSION_TYPE'] == 'wayland'
        assert not actual.get('DISPLAY')
        assert not run(['getcap', '/usr/bin/kwin_wayland'], actual).strip()
        assert not {'Xwayland', 'Xorg'} & set(run(['ps', '-e', '-o', 'comm='], actual).splitlines())
        actual['NATIVE_BROWSER_GATE'] = '1'
        subprocess.run(['python3', '/tests/native-ui.py'], env=actual, check=True, timeout=90)
        assert not {'Xwayland', 'Xorg'} & set(run(['ps', '-e', '-o', 'comm='], actual).splitlines())
        if env.get('GPU_GATE_REQUIRE_DOCUMENT_PORTAL') == '1':
            from gi.repository import Gio
            reply = Gio.bus_get_sync(Gio.BusType.SESSION).call_sync(
                'org.freedesktop.portal.Documents', '/org/freedesktop/portal/documents',
                'org.freedesktop.portal.Documents', 'GetMountPoint', None, None,
                Gio.DBusCallFlags.NONE, 10000, None)
            mount = bytes(reply.unpack()[0]).rstrip(b'\0').decode()
            assert os.path.ismount(mount), f'Document portal FUSE mount missing: {mount}'
            event('GPU_DOCUMENT_PORTAL_PASS')
        run(['pgrep', '-x', 'clustercut'], actual)
        assert ':4654 ' in run(['ss', '-lun'], actual) and ':4654 ' in run(['ss', '-ltn'], actual)
        identity = home / '.config/app.clustercut.clustercut/device_id'
        assert identity.is_file()
        saved_identity = state_home / 'gpu-test-clustercut-identity'
        if saved_identity.exists():
            assert saved_identity.read_bytes() == identity.read_bytes()
        else:
            saved_identity.write_bytes(identity.read_bytes())
        gpg_roundtrip(actual, gpg_home)
        assert (gpg_home / 'public-keys.d/pubring.db.lock').exists()
        stopped_agent = int(run(['gpg-connect-agent', 'GETINFO pid', '/bye'], actual).split('D ')[1].splitlines()[0])
        shutdown_deadline = time.monotonic() + 25
        if case == 'logout':
            run(['gdbus', 'call', '--session', '--dest', 'org.kde.Shutdown',
                 '--object-path', '/Shutdown', '--method', 'org.kde.Shutdown.logout'], actual)
        elif case == 'compositor':
            os.kill(info['pid'], signal.SIGKILL)
        elif case == 'parent':
            event('GPU_GATE_PARENT_LOSS_READY')
        else:
            desktop.terminate()
        status = desktop.wait(timeout=20)
        expected_status = 0 if case == 'logout' else 143
        assert status != 0 if case in ('compositor', 'parent') else status == expected_status, status
        if env.get('GNUPGHOME'):
            # Do not accidentally spawn a replacement agent and call that preservation.
            preserved = run(['gpg-connect-agent', '--no-autostart', 'GETINFO pid', '/bye'], actual)
            assert int(preserved.split('D ')[1].splitlines()[0]) == stopped_agent
            run(['gpgconf', '--homedir', str(gpg_home), '--kill', 'all'], actual)
        else:
            assert not (gpg_home / 'public-keys.d/pubring.db.lock').exists()
        names = ['plasmashell', 'kwin_wayland', 'clustercut', 'konsole']
        if not env.get('GNUPGHOME'):
            names += ['gpg-agent', 'keyboxd']
        for name in names:
            while True:
                found = subprocess.run(['pgrep', '-u', str(os.getuid()), '-x', name],
                                       stdout=subprocess.DEVNULL, timeout=2)
                if found.returncode != 0 or time.monotonic() >= shutdown_deadline:
                    break
                time.sleep(.05)
            assert found.returncode != 0, 'Client/daemon survived bounded shutdown: ' + name
        event('GPU_GATE_RESULT', passed=True, case=case, requested_rate=rate,
              custom_gnupghome=bool(env.get('GNUPGHOME')), bounded_teardown=True)
    finally:
        if marker and marker.poll() is None:
            marker.terminate()
            marker.wait(timeout=5)
        if desktop and desktop.poll() is None:
            desktop.terminate()
            desktop.wait(timeout=20)
        if env.get('GNUPGHOME'):
            subprocess.run(['gpgconf', '--homedir', str(gpg_home), '--kill', 'all'], env=env, timeout=10)
        audio.close()
        log.seek(0)
        print(log.read(), flush=True)
        log.close()


if __name__ == '__main__':
    main()
