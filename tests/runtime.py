#!/usr/bin/env python3
"""Exercise the root init hook against real sockets in a disposable container."""
import os
from types import SimpleNamespace
from pathlib import Path
import socket
import stat
import subprocess
import tempfile
import unittest
import sys
from unittest import mock

sys.path.insert(0, '/opt/wolf-plasma')
import session

HOOK = '/etc/cont-init.d/05-plasma-runtime.sh'


class RuntimeTests(unittest.TestCase):
    def test_native_compositor_failure_wins_over_clean_desktop_exit(self):
        with tempfile.TemporaryDirectory() as name, socket.socket(socket.AF_UNIX) as parent:
            state = Path(name)
            path = str(state / 'parent')
            parent.bind(path)
            (state / 'compositor-exited').write_text('0')
            self.assertEqual(session.supervise(SimpleNamespace(poll=lambda: 0), state,
                                              {}, path, 1280, 720, 90), 1)

    def test_parent_loss_and_changed_mode_fail_closed(self):
        with tempfile.TemporaryDirectory() as name, socket.socket(socket.AF_UNIX) as parent:
            state = Path(name)
            path = str(state / 'parent')
            parent.bind(path)
            for result in (RuntimeError('parent disconnected'), [
                    {'width': 1280, 'height': 720, 'refresh_mHz': 60000}]):
                with self.subTest(result=result), mock.patch.object(session, 'parent_modes') as modes:
                    if isinstance(result, Exception):
                        modes.side_effect = result
                    else:
                        modes.return_value = result
                    with self.assertRaises(RuntimeError):
                        session.supervise(SimpleNamespace(poll=lambda: None), state,
                                          {}, path, 1280, 720, 90)

    def test_parent_socket_replacement_is_not_adopted(self):
        with tempfile.TemporaryDirectory() as name, socket.socket(socket.AF_UNIX) as parent, \
             socket.socket(socket.AF_UNIX) as replacement:
            state = Path(name)
            path = state / 'parent'
            parent.bind(str(path))
            def replace(_):
                path.unlink()
                replacement.bind(str(path))
                return [{'width': 1280, 'height': 720, 'refresh_mHz': 90000}]
            with mock.patch.object(session, 'parent_modes', side_effect=replace), \
                 mock.patch.object(session, 'native_ready', return_value=True), \
                 mock.patch.object(session.time, 'monotonic', side_effect=[0, 1, 3]), \
                 mock.patch.object(session.time, 'sleep'):
                with self.assertRaisesRegex(RuntimeError, 'socket replaced'):
                    session.supervise(SimpleNamespace(poll=lambda: None), state,
                                      {}, str(path), 1280, 720, 90)

    def run_hook(self, directory, display=None):
        env = os.environ.copy()
        env.pop('WOLF_PLASMA_PARENT_WAYLAND', None)
        env.pop('WAYLAND_DISPLAY', None)
        env.update(PUID='1001', PGID='1001', XDG_RUNTIME_DIR=str(directory))
        if display is not None:
            env['WAYLAND_DISPLAY'] = display
        return subprocess.run(['bash', '-ec', f'source {HOOK}'], env=env,
                              capture_output=True, text=True)

    def test_only_parent_socket_becomes_connectable(self):
        with tempfile.TemporaryDirectory(prefix='wolf-sockets-') as name:
            directory = Path(name)
            directory.chmod(0o755)
            with socket.socket(socket.AF_UNIX) as parent, socket.socket(socket.AF_UNIX) as neighbour:
                path = directory / 'wayland-test'
                other = directory / 'unrelated-socket'
                parent.bind(str(path))
                parent.listen(1)
                neighbour.bind(str(other))
                path.chmod(0o755)
                other.chmod(0o755)
                result = self.run_hook(directory, path.name)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((path.stat().st_uid, path.stat().st_gid), (1001, 1001))
                self.assertEqual(directory.stat().st_uid, 0)
                self.assertEqual(other.stat().st_uid, 0)
                probe = subprocess.run(['gosu', '1001:1001', 'python3', '-c',
                                        'import socket,sys;s=socket.socket(socket.AF_UNIX);s.connect(sys.argv[1])',
                                        str(path)], capture_output=True, text=True)
                self.assertEqual(probe.returncode, 0, probe.stderr)

    def test_private_runtime(self):
        with tempfile.TemporaryDirectory() as name:
            result = self.run_hook(Path(name))
            self.assertEqual(result.returncode, 0, result.stderr)
            runtime = Path('/run/user/1001').stat()
            self.assertEqual((runtime.st_uid, runtime.st_gid, stat.S_IMODE(runtime.st_mode)),
                             (1001, 1001, 0o700))


if __name__ == '__main__':
    unittest.main(verbosity=2)
