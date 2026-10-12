#!/usr/bin/env python3
"""Exercise the root init hook against real sockets in a disposable container."""
import os
from pathlib import Path
import socket
import stat
import subprocess
import tempfile
import unittest

HOOK = '/etc/cont-init.d/05-plasma-runtime.sh'


class RuntimeTests(unittest.TestCase):
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

    def test_private_runtime_and_legacy_socket_directories(self):
        with tempfile.TemporaryDirectory() as name:
            result = self.run_hook(Path(name))
            self.assertEqual(result.returncode, 0, result.stderr)
            runtime = Path('/run/user/1001').stat()
            self.assertEqual((runtime.st_uid, runtime.st_gid, stat.S_IMODE(runtime.st_mode)),
                             (1001, 1001, 0o700))
            for directory in ('/tmp/.X11-unix', '/tmp/.ICE-unix'):
                with self.subTest(directory=directory):
                    info = Path(directory).stat()
                    self.assertEqual((info.st_uid, stat.S_IMODE(info.st_mode)), (0, 0o1777))


if __name__ == '__main__':
    unittest.main(verbosity=2)
