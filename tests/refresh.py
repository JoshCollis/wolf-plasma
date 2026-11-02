#!/usr/bin/env python3
"""Refresh contract tests; no user home, compositor or desktop required."""
import importlib.util
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'overlay/opt/wolf-plasma/refresh.py'
if not MODULE.exists():
    MODULE = Path('/opt/wolf-plasma/refresh.py')


def load():
    assert MODULE.exists(), 'Missing negotiated-refresh contract implementation'
    spec = importlib.util.spec_from_file_location('refresh', MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RefreshTests(unittest.TestCase):
    def test_validated_negotiated_rate(self):
        refresh = load()
        for rate in (30, 60, 90, 120, 144):
            self.assertEqual(refresh.negotiated_refresh({'GAMESCOPE_REFRESH': str(rate)}), rate)
        self.assertEqual(refresh.negotiated_refresh({}), 60)
        for rate in ('0', '-1', '145', '90.0', '', 'bogus'):
            with self.subTest(rate=rate), self.assertRaises(RuntimeError):
                refresh.negotiated_refresh({'GAMESCOPE_REFRESH': rate})

    def test_parent_agreement_rejects_relabelled_and_ambiguous_output(self):
        refresh = load()
        for rate in (60, 90, 120, 144):
            refresh.require_parent_mode([{'width': 1920, 'height': 1200, 'refresh_mHz': rate * 1000}], 1920, 1200, rate)
        for modes in ([], [{'width': 1920, 'height': 1200, 'refresh_mHz': 60000}],
                      [{'width': 1280, 'height': 720, 'refresh_mHz': 144000}],
                      [{'width': 1920, 'height': 1200, 'refresh_mHz': 0}]):
            with self.subTest(modes=modes), self.assertRaises(RuntimeError):
                refresh.require_parent_mode(modes, 1920, 1200, 144)
        mode = {'width': 1920, 'height': 1200, 'refresh_mHz': 144000}
        with self.assertRaises(RuntimeError):
            refresh.require_parent_mode([mode, mode], 1920, 1200, 144)

    def test_real_socket_registry_two_roundtrips_and_current_flag(self):
        refresh = load()
        with tempfile.TemporaryDirectory() as name:
            path = str(Path(name) / 'parent')
            errors = []
            with socket.socket(socket.AF_UNIX) as server:
                server.bind(path)
                server.listen()
                def peer():
                    try:
                        with server.accept()[0] as client:
                            def request():
                                header = client.recv(8, socket.MSG_WAITALL)
                                obj, word = struct.unpack('II', header)
                                return obj, word & 65535, client.recv((word >> 16) - 8, socket.MSG_WAITALL)
                            def event(obj, opcode, payload):
                                packet = struct.pack('II', obj, ((8 + len(payload)) << 16) | opcode) + payload
                                # Exercise fragmented stream messages, not just one recv/event.
                                client.sendall(packet[:3]); client.sendall(packet[3:])
                            self.assertEqual(request(), (1, 1, struct.pack('I', 2)))
                            _, _, data = request(); sync = struct.unpack('I', data)[0]
                            interface = b'wl_output\0'
                            event(2, 0, struct.pack('II', 7, len(interface)) + interface + b'\0' * 2 + struct.pack('I', 2))
                            event(sync, 0, struct.pack('I', 1))
                            _, _, data = request(); output = struct.unpack('I', data[-4:])[0]
                            self.assertEqual(struct.unpack('I', data[-8:-4])[0], 2)
                            _, _, data = request(); sync = struct.unpack('I', data)[0]
                            event(output, 1, struct.pack('Iiii', 2, 1920, 1200, 60000))
                            event(output, 1, struct.pack('Iiii', 3, 1920, 1200, 90000))
                            event(sync, 0, struct.pack('I', 2))
                    except BaseException as exc:
                        errors.append(exc)
                thread = threading.Thread(target=peer)
                thread.start()
                try:
                    self.assertEqual(refresh.parent_modes(path), [{'width': 1920, 'height': 1200, 'refresh_mHz': 90000}])
                finally:
                    thread.join(timeout=6)
                self.assertFalse(thread.is_alive())
                if errors:
                    raise errors[0]

    def test_actual_session_rejects_mismatched_parent_before_launch(self):
        source_path = ROOT / 'overlay/opt/wolf-plasma/session.py'
        if not source_path.exists():
            source_path = Path('/opt/wolf-plasma/session.py')
        sys.path.insert(0, str(source_path.parent))
        import session
        with tempfile.TemporaryDirectory() as name, socket.socket(socket.AF_UNIX) as parent:
            path = str(Path(name) / 'parent')
            parent.bind(path)
            env = dict(os.environ, XDG_RUNTIME_DIR=name, WAYLAND_DISPLAY=path,
                       GAMESCOPE_WIDTH='1280', GAMESCOPE_HEIGHT='720', GAMESCOPE_REFRESH='90')
            with mock.patch.dict(os.environ, env, clear=True), \
                 mock.patch.object(session, 'GpgLifecycle'), \
                 mock.patch.object(session, 'parent_modes', return_value=[{
                     'width': 1280, 'height': 720, 'refresh_mHz': 60000}]), \
                 mock.patch.object(session.subprocess, 'Popen') as launch:
                with self.assertRaisesRegex(RuntimeError, 'parent/request mismatch'):
                    session.main()
                launch.assert_not_called()
            session.gpg_lifecycle = None


if __name__ == '__main__':
    unittest.main(verbosity=2)
