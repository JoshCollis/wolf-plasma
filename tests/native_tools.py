"""Test-only native KWin inspection and compositor screenshot helpers."""
import json
import os
from pathlib import Path
import tempfile
import time

from gi.repository import Gio, GLib


def call(path, interface, method, parameters=None):
    return Gio.bus_get_sync(Gio.BusType.SESSION).call_sync(
        'org.kde.KWin', path, interface, method, parameters, None,
        Gio.DBusCallFlags.NONE, 5000, None)


def script(body):
    connection = Gio.bus_get_sync(Gio.BusType.SESSION)
    result = []
    node = Gio.DBusNodeInfo.new_for_xml('<node><interface name="org.wolfplasma.Probe">'
                                     '<method name="Report"><arg type="s" direction="in"/>'
                                     '</method></interface></node>')
    def report(conn, sender, path, interface, method, args, invocation):
        result.append(json.loads(args.unpack()[0]))
        invocation.return_value(None)
    registration = connection.register_object('/Probe', node.interfaces[0], report, None, None)
    with tempfile.TemporaryDirectory(prefix='kwin-test-', dir=os.environ['XDG_RUNTIME_DIR']) as name:
        file = Path(name) / 'probe.js'
        plugin = 'native-test-' + file.parent.name
        file.write_text('const result = (() => {' + body + '})();\n'
                        f'callDBus({json.dumps(connection.get_unique_name())}, "/Probe", '
                        '"org.wolfplasma.Probe", "Report", JSON.stringify(result));\n')
        number = call('/Scripting', 'org.kde.kwin.Scripting', 'loadScript',
                      GLib.Variant('(ss)', (str(file), plugin))).unpack()[0]
        try:
            call(f'/Scripting/Script{number}', 'org.kde.kwin.Script', 'run')
            deadline = time.monotonic() + 5
            while not result and time.monotonic() < deadline:
                GLib.MainContext.default().iteration(False)
                time.sleep(.01)
            assert result, 'KWin script did not report its native window state'
            return result[0]
        finally:
            call('/Scripting', 'org.kde.kwin.Scripting', 'unloadScript', GLib.Variant('(s)', (plugin,)))
            connection.unregister_object(registration)


def windows():
    return script('return workspace.windowList().map(w => ({pid:w.pid, '
                  'caption:w.caption, app:w.resourceClass, id:w.internalId.toString()}));')


def screenshot():
    connection = Gio.bus_get_sync(Gio.BusType.SESSION)
    fd = os.memfd_create('native-compositor-frame', os.MFD_CLOEXEC)
    try:
        descriptors = Gio.UnixFDList.new()
        index = descriptors.append(fd)
        reply, _ = connection.call_with_unix_fd_list_sync(
            'org.kde.KWin.ScreenShot2', '/org/kde/KWin/ScreenShot2',
            'org.kde.KWin.ScreenShot2', 'CaptureActiveScreen',
            GLib.Variant('(a{sv}h)', ({'hide-caller-windows': GLib.Variant('b', False)}, index)),
            None, Gio.DBusCallFlags.NONE, 10000, descriptors, None)
        info = reply.unpack()[0]
        size = info['stride'] * info['height']
        deadline = time.monotonic() + 10
        while os.fstat(fd).st_size < size and time.monotonic() < deadline:
            time.sleep(.02)
        assert os.fstat(fd).st_size == size, info
        return info, os.pread(fd, size, 0)
    finally:
        os.close(fd)
