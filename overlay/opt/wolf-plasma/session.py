#!/usr/bin/env python3
"""Supervise one native Plasma/KWin session and its unchanged Wolf parent."""
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import tempfile
import time

from gpg_lifecycle import GpgLifecycle
from refresh import negotiated_refresh, parent_modes, require_parent_mode
from output_publication import publish_current_mode

children = []
gpg_lifecycle = None
PROBE_FAILURE_GRACE = 10
LOGOUT_GRACE = 10


def stop(signum=None, frame=None):
    global gpg_lifecycle
    for child in reversed(children):
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 5
    while any(c.poll() is None for c in children) and time.monotonic() < deadline:
        time.sleep(0.1)
    for child in children:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait()
    children.clear()
    if gpg_lifecycle is not None:
        gpg_lifecycle.shutdown()
        gpg_lifecycle = None
    if signum:
        raise SystemExit(128 + signum)


for sig in (signal.SIGTERM, signal.SIGINT):
    signal.signal(sig, stop)


def main():
    global gpg_lifecycle
    env = os.environ.copy()
    runtime = Path(env["XDG_RUNTIME_DIR"])
    info = runtime.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise RuntimeError("XDG_RUNTIME_DIR must be owned by the desktop UID, mode 0700")
    parent = env.get("WOLF_PLASMA_PARENT_WAYLAND", env.get("WAYLAND_DISPLAY", ""))
    if not parent.startswith("/"):
        parent = str(runtime / parent)
    if not Path(parent).is_socket():
        raise RuntimeError(f"Wolf parent Wayland socket missing: {parent}")
    parent_identity = Path(parent).stat()
    # Hold the home lease before any desktop client can launch GPG, and until
    # desktop clients and the home-scoped GPG daemons have been stopped.
    gpg_lifecycle = GpgLifecycle(env)
    gpg_lifecycle.start()
    width = int(env.get("GAMESCOPE_WIDTH", "1920"))
    height = int(env.get("GAMESCOPE_HEIGHT", "1080"))
    if not (320 <= width <= 16384 and 240 <= height <= 16384):
        raise RuntimeError("Invalid Wolf client dimensions")
    rate = negotiated_refresh(env)
    require_parent_mode(parent_modes(parent), width, height, rate)
    for key in ("DISPLAY", "XAUTHORITY", "WAYLAND_SOCKET", "WOLF_PLASMA_PARENT_WAYLAND",
                "DBUS_SESSION_BUS_ADDRESS", "DBUS_SESSION_BUS_PID", "SESSION_MANAGER", "KDEWM",
                "GDK_BACKEND", "QT_QPA_PLATFORM", "QT_STYLE_OVERRIDE", "GTK_THEME",
                "XDG_SESSION_DESKTOP", "DESKTOP_SESSION"):
        env.pop(key, None)
    env.update(XDG_CURRENT_DESKTOP="KDE", XDG_SESSION_TYPE="wayland", DESKTOP_SESSION="plasmawayland",
                XDG_SESSION_DESKTOP="KDE", KDE_FULL_SESSION="true", KDE_SESSION_VERSION="6",
                WAYLAND_DISPLAY=parent, WOLF_PLASMA_PARENT_DISPLAY=parent,
                GAMESCOPE_WIDTH=str(width), GAMESCOPE_HEIGHT=str(height), GAMESCOPE_REFRESH=str(rate),
                QT_QPA_PLATFORM="wayland", GDK_BACKEND="wayland", MOZ_ENABLE_WAYLAND="1",
                ELECTRON_OZONE_PLATFORM_HINT="wayland",
                XDG_DATA_DIRS=f'{env["HOME"]}/.local/share/flatpak/exports/share:/var/lib/flatpak/exports/share:/usr/local/share:/usr/share')
    with tempfile.TemporaryDirectory(prefix='wolf-plasma-', dir=runtime) as directory:
        env['WOLF_PLASMA_SESSION_STATE'] = directory
        children.append(subprocess.Popen(["dbus-run-session", "--", "/opt/wolf-plasma/desktop.sh"],
                                         env=env, start_new_session=True))
        try:
            return supervise(children[-1], Path(directory), env, parent, width, height, rate,
                             identity=parent_identity)
        finally:
            stop()


def compositor_status(state):
    """None: live/not launched; int: observed exit; 'pending': observer race."""
    exited = state / 'compositor-exited'
    if exited.exists():
        return int(exited.read_text())
    info = state / 'compositor.json'
    if not info.exists():
        return None
    pid = json.loads(info.read_text())['pid']
    try:
        if Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0] != 'Z':
            return None
    except FileNotFoundError:
        pass
    return 'pending'


def supervise(desktop, state, env, parent, width, height, rate, identity=None):
    identity = identity or Path(parent).stat()
    deadline = time.monotonic() + 60
    ready, next_probe = False, 0
    unavailable_since, closing_since = None, None
    while True:
        # A known signal/nonzero compositor failure always wins over Plasma 0.
        exited = compositor_status(state)
        if isinstance(exited, int) and exited != 0:
            print("Native KWin exited; recreate the desktop session", flush=True)
            return 1
        status = desktop.poll()
        if status is not None and status != 0:
            return status if status >= 0 else 128 - status
        now = time.monotonic()
        closing = exited is not None
        if closing:
            if not ready:
                return 1
            if closing_since is None:
                closing_since = now
            if now - closing_since >= LOGOUT_GRACE:
                print('KWin stopped without a completed clean desktop logout', flush=True)
                return 1
        if status == 0 and not ready:
            return 1
        if now >= next_probe or status == 0:
            # Never continue rendering after parent disappearance, renegotiation
            # or replacement. Every probe opens the original socket, not a guess.
            current = Path(parent).stat()
            if (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
                raise RuntimeError('Wolf parent socket replaced; recreate the lobby')
            try:
                require_parent_mode(parent_modes(parent), width, height, rate)
                # Classic Plasma logout quits KWin BEFORE startplasma completes.
                # Do not probe an intentionally closing child socket. Its exit
                # must still be observed as 0 and accompanied by desktop 0.
                healthy = True if closing or status == 0 else native_ready(
                    state, env, width, height, rate, allow_mode_publication=not ready)
            except (TimeoutError, subprocess.TimeoutExpired) as exc:
                # An inconclusive IPC probe is not evidence of process/output
                # loss. Retry with a bounded grace; explicit disconnect, inode
                # replacement and mode mismatch are NOT caught here.
                if ready:
                    observed = time.monotonic()
                    if unavailable_since is None:
                        unavailable_since = observed
                    if observed - unavailable_since >= PROBE_FAILURE_GRACE:
                        raise RuntimeError('Session probe unavailable beyond bounded grace') from exc
            else:
                unavailable_since = None
                if healthy and not ready:
                    print(f"Native Plasma ready: {width}x{height}@{rate}Hz", flush=True)
                    ready = True
                elif ready and not healthy:
                    raise RuntimeError('Native compositor/output/desktop lost readiness')
                if status == 0:
                    # Parent IPC may block while the compositor exits. Classify
                    # fresh terminal evidence before committing logout success.
                    if compositor_status(state) != exited or desktop.poll() != status:
                        continue
                    if exited != 'pending':
                        return 0
            next_probe = now + 1
        if not ready and now >= deadline:
            print("Native KWin/Plasma did not become ready within 60 seconds", flush=True)
            return 1
        time.sleep(0.2)


def native_ready(state, env, width, height, rate, *, allow_mode_publication=True):
    info, bus = state / 'compositor.json', state / 'bus'
    if not info.exists() or not bus.exists():
        return False
    client = json.loads(info.read_text())
    socket = str(Path(env['XDG_RUNTIME_DIR']) / client['socket'])
    probe_env = env | {'DBUS_SESSION_BUS_ADDRESS': bus.read_text().strip(),
                       'WAYLAND_DISPLAY': socket}
    try:
        # Wrapper name registration alone precedes real compositing readiness.
        result = subprocess.run(['dbus-send', '--session', '--type=method_call', '--print-reply',
            '--dest=org.kde.KWin', '/Compositor', 'org.freedesktop.DBus.Properties.Get',
            'string:org.kde.kwin.Compositing', 'string:active'], env=probe_env,
            capture_output=True, text=True, timeout=2)
        if result.returncode:
            raise TimeoutError('Native compositor D-Bus probe unavailable')
        if 'boolean true' not in result.stdout:
            return False
        modes = parent_modes(socket)
        if (allow_mode_publication and len(modes) == 1
                and (modes[0]['width'], modes[0]['height']) == (width, height)
                and abs(modes[0]['refresh_mHz'] - rate * 1000) > 500
                and publish_current_mode(state, probe_env, width, height, rate)):
            modes = parent_modes(socket)
        require_parent_mode(modes, width, height, rate)
        return subprocess.run(['pgrep', '-u', str(os.getuid()), '-x', 'plasmashell'],
                              stdout=subprocess.DEVNULL).returncode == 0
    except (TimeoutError, subprocess.TimeoutExpired):
        raise
    except (OSError, RuntimeError):
        # Readiness still requires real wl_output state. Startup synchronization
        # may only publish a backend mode already learned from parent feedback.
        return False


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    finally:
        stop()
