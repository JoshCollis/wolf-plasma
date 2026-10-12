#!/usr/bin/env python3
"""Supervise rootful Xwayland and exactly one private Plasma session bus."""
import os
from pathlib import Path
import signal
import stat
import subprocess
import time

children = []


def stop(signum=None, frame=None):
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
    if signum:
        raise SystemExit(128 + signum)


for sig in (signal.SIGTERM, signal.SIGINT):
    signal.signal(sig, stop)


def main():
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
    # An auth cookie and no TCP listener; no xhost/access-control bypass.
    env["DISPLAY"] = ":0"
    env["XAUTHORITY"] = str(runtime / "Xauthority")
    Path(env["XAUTHORITY"]).touch(mode=0o600)
    subprocess.run(["xauth", "-f", env["XAUTHORITY"], "add", ":0", ".", os.urandom(16).hex()], check=True)
    xenv = env | {"WAYLAND_DISPLAY": parent}
    width = int(env.get("GAMESCOPE_WIDTH", "1920"))
    height = int(env.get("GAMESCOPE_HEIGHT", "1080"))
    if not (320 <= width <= 16384 and 240 <= height <= 16384):
        raise RuntimeError("Invalid Wolf client dimensions")
    children.append(subprocess.Popen(
        ["Xwayland", ":0", "-fullscreen", "-geometry", f"{width}x{height}",
         "-nolisten", "tcp", "-noreset", "-auth", env["XAUTHORITY"]],
        env=xenv, start_new_session=True))
    deadline = time.monotonic() + 30
    while True:
        if children[0].poll() is not None:
            raise RuntimeError(f"Xwayland exited before readiness: {children[0].returncode}")
        try:
            probe = subprocess.run(["xdpyinfo"], env=env, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=1)
            if probe.returncode == 0:
                break
        except subprocess.TimeoutExpired:
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError("Xwayland did not become ready within 30 seconds")
        time.sleep(0.1)
    for key in ("WAYLAND_DISPLAY", "WAYLAND_SOCKET", "WOLF_PLASMA_PARENT_WAYLAND",
                "DBUS_SESSION_BUS_ADDRESS", "DBUS_SESSION_BUS_PID", "SESSION_MANAGER", "KDEWM",
                "GDK_BACKEND", "QT_QPA_PLATFORM", "QT_STYLE_OVERRIDE", "GTK_THEME",
                "XDG_SESSION_DESKTOP", "DESKTOP_SESSION"):
        env.pop(key, None)
    env.update(XDG_CURRENT_DESKTOP="KDE", XDG_SESSION_TYPE="x11", DESKTOP_SESSION="plasma",
               XDG_SESSION_DESKTOP="KDE", KDE_FULL_SESSION="true", KDE_SESSION_VERSION="6",
               XDG_DATA_DIRS=f'{env["HOME"]}/.local/share/flatpak/exports/share:/var/lib/flatpak/exports/share:/usr/local/share:/usr/share')
    children.append(subprocess.Popen(["dbus-run-session", "--", "/opt/wolf-plasma/desktop.sh"],
                                     env=env, start_new_session=True))
    deadline = time.monotonic() + 45
    ready = False
    while True:
        desktop = children[1].poll()
        if desktop is not None:
            return desktop if desktop >= 0 else 128 - desktop
        if children[0].poll() is not None:
            print("Xwayland exited while Plasma was running", flush=True)
            return 1
        healthy = all(subprocess.run(["pgrep", "-u", str(os.getuid()), "-x", name],
                                     stdout=subprocess.DEVNULL).returncode == 0
                      for name in ("kwin_x11", "plasmashell"))
        if healthy:
            ready = True
        elif ready or time.monotonic() >= deadline:
            print("KWin or plasmashell failed to start/stay running", flush=True)
            return 1
        time.sleep(0.2)


try:
    raise SystemExit(main())
finally:
    stop()
