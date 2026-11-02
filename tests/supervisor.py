#!/usr/bin/env python3
"""Execute the real supervisor/health-probe code with controlled IPC and exits."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / 'overlay/opt/wolf-plasma/session.py'
if not SOURCE.exists():
    SOURCE = Path('/opt/wolf-plasma/session.py')
sys.path.insert(0, str(SOURCE.parent))
spec = importlib.util.spec_from_file_location('session_under_test', SOURCE)
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)


class Clock:
    def __init__(self):
        self.value = 0
        self.hook = lambda: None

    def now(self):
        return self.value

    def sleep(self, delay):
        self.value += delay
        self.hook()
        assert self.value <= 120, 'Supervisor failed to bound a pending probe/exit'


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='native-supervisor-')
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.parent = self.state / 'parent'
        self.server = socket.socket(socket.AF_UNIX)
        self.addCleanup(self.server.close)
        self.server.bind(str(self.parent))
        self.child_socket = self.state / 'client'
        self.child = socket.socket(socket.AF_UNIX)
        self.addCleanup(self.child.close)
        self.child.bind(str(self.child_socket))
        self.live_info = {'pid': os.getpid(), 'socket': 'client'}
        (self.state / 'compositor.json').write_text(json.dumps(self.live_info))
        (self.state / 'bus').write_text('unix:path=/private-fixture-bus')
        self.clock = Clock()
        self.desktop_status = None
        self.dbus_calls = 0
        self.parent_calls = 0
        self.dbus_action = lambda: None
        self.parent_action = lambda: None
        self.mode = {'width': 800, 'height': 600, 'refresh_mHz': 60000}

    def ipc(self, argv, **kwargs):
        if argv[0] == 'dbus-send':
            self.dbus_calls += 1
            self.dbus_action()
            return subprocess.CompletedProcess(argv, 0, 'variant boolean true', '')
        self.assertEqual(argv[0], 'pgrep')
        return subprocess.CompletedProcess(argv, 0)

    def modes(self, path):
        if path == str(self.parent):
            self.parent_calls += 1
            self.parent_action()
        return [dict(self.mode)]

    def supervise(self):
        desktop = mock.Mock()
        desktop.poll.side_effect = lambda: self.desktop_status
        with mock.patch.object(session.time, 'monotonic', self.clock.now), \
             mock.patch.object(session.time, 'sleep', self.clock.sleep), \
             mock.patch.object(session.subprocess, 'run', self.ipc), \
             mock.patch.object(session, 'parent_modes', self.modes):
            return session.supervise(desktop, self.state, {'XDG_RUNTIME_DIR': str(self.state)},
                                     str(self.parent), 800, 600, 60)

    def exit_record(self, status):
        (self.state / 'compositor-exited').write_text(str(status))

    def test_single_dbus_timeout_recovers_without_teardown(self):
        def action():
            if self.dbus_calls == 2:
                self.clock.value += 2
                raise subprocess.TimeoutExpired(['dbus-send'], 2)
            if self.dbus_calls == 3:
                self.desktop_status = 0
        self.dbus_action = action
        self.assertEqual(self.supervise(), 0)
        self.assertEqual(self.dbus_calls, 3, 'Recovery probe was not attempted')

    def test_single_parent_timeout_recovers_without_teardown(self):
        def parent():
            if self.parent_calls == 2:
                self.clock.value += 5
                raise TimeoutError('parent output probe timed out')
        def dbus():
            if self.dbus_calls == 2:
                self.desktop_status = 0
        self.parent_action, self.dbus_action = parent, dbus
        self.assertEqual(self.supervise(), 0)
        self.assertGreaterEqual(self.parent_calls, 3)

    def test_persistent_dbus_timeouts_fail_with_bounded_grace(self):
        def action():
            if self.dbus_calls >= 2:
                self.clock.value += 2
                raise subprocess.TimeoutExpired(['dbus-send'], 2)
        self.dbus_action = action
        with self.assertRaisesRegex(RuntimeError, 'probe.*unavailable|unavailable.*probe'):
            self.supervise()
        self.assertGreaterEqual(self.clock.value, 10)
        self.assertLess(self.clock.value, 25)

    def test_persistent_parent_timeouts_fail_with_bounded_grace(self):
        def action():
            if self.parent_calls >= 2:
                self.clock.value += 5
                raise TimeoutError('parent output probe timed out')
        self.parent_action = action
        with self.assertRaisesRegex(RuntimeError, 'probe.*unavailable|unavailable.*probe'):
            self.supervise()
        self.assertGreaterEqual(self.clock.value, 10)
        self.assertLess(self.clock.value, 30)

    def test_parent_mode_change_is_not_a_transient_probe_failure(self):
        def action():
            if self.parent_calls == 2:
                self.mode['refresh_mHz'] = 90000
        self.parent_action = action
        with self.assertRaisesRegex(RuntimeError, 'parent/request mismatch'):
            self.supervise()
        self.assertLess(self.clock.value, 2)

    def test_parent_socket_loss_is_not_a_transient_probe_failure(self):
        self.clock.hook = lambda: self.parent.unlink() if self.parent.exists() else None
        with self.assertRaises(OSError):
            self.supervise()
        self.assertLess(self.clock.value, 2)

    def test_parent_mode_change_during_transient_grace_still_fails_immediately(self):
        def action():
            if self.dbus_calls == 2:
                self.mode['refresh_mHz'] = 90000
                raise subprocess.TimeoutExpired(['dbus-send'], 2)
        self.dbus_action = action
        with self.assertRaisesRegex(RuntimeError, 'parent/request mismatch'):
            self.supervise()
        self.assertLess(self.clock.value, 3)

    def test_normal_logout_clean_compositor_overlaps_clean_desktop(self):
        def logout():
            self.exit_record(0)
            self.desktop_status = 0
        self.clock.hook = logout
        self.assertEqual(self.supervise(), 0)

    def test_normal_logout_clean_compositor_precedes_clean_desktop(self):
        def logout():
            self.exit_record(0)
            if self.clock.value >= .8:
                self.desktop_status = 0
        self.clock.hook = logout
        self.assertEqual(self.supervise(), 0)
        self.assertGreaterEqual(self.clock.value, .8)

    def test_observer_status_publication_race_does_not_break_clean_logout(self):
        def logout():
            (self.state / 'compositor.json').write_text(json.dumps({'pid': 2147483647, 'socket': 'client'}))
            self.desktop_status = 0
            if self.clock.value >= .4:
                self.exit_record(0)
        self.clock.hook = logout
        self.assertEqual(self.supervise(), 0)

    def test_unexpected_clean_compositor_exit_cannot_succeed(self):
        self.clock.hook = lambda: self.exit_record(0)
        self.assertEqual(self.supervise(), 1)
        self.assertLess(self.clock.value, 15)

    def test_missing_exit_status_cannot_mask_failure_with_clean_desktop(self):
        def missing_status():
            (self.state / 'compositor.json').write_text(json.dumps({'pid': 2147483647, 'socket': 'client'}))
            self.desktop_status = 0
        self.clock.hook = missing_status
        self.assertEqual(self.supervise(), 1)
        self.assertLess(self.clock.value, 15)

    def test_clean_logout_does_not_accept_a_changed_parent(self):
        def logout():
            self.exit_record(0)
            self.desktop_status = 0
            self.mode['refresh_mHz'] = 90000
        self.clock.hook = logout
        with self.assertRaisesRegex(RuntimeError, 'parent/request mismatch'):
            self.supervise()

    def final_parent_probe_exit(self, status):
        self.clock.hook = lambda: setattr(self, 'desktop_status', 0)
        def during_probe():
            if self.parent_calls == 2:
                if status is None:
                    (self.state / 'compositor.json').write_text(json.dumps(
                        {'pid': 2147483647, 'socket': 'client'}))
                else:
                    record = self.state / 'compositor-exited.tmp'
                    record.write_text(str(status))
                    record.replace(self.state / 'compositor-exited')
                self.clock.value += 1
        self.parent_action = during_probe
        self.assertEqual(self.supervise(), 1)
        self.assertGreaterEqual(self.parent_calls, 2)
        self.assertLess(self.clock.value, 15)

    def test_signal_during_final_parent_probe_wins_over_clean_desktop(self):
        self.final_parent_probe_exit(-9)

    def test_nonzero_during_final_parent_probe_wins_over_clean_desktop(self):
        self.final_parent_probe_exit(17)

    def test_missing_record_during_final_parent_probe_cannot_succeed(self):
        self.final_parent_probe_exit(None)

    def test_signal_or_nonzero_compositor_failure_wins_over_clean_desktop(self):
        for status in (-15, -9, 17, 139):
            with self.subTest(status=status):
                self.setUp()
                def failure():
                    self.exit_record(status)
                    self.desktop_status = 0
                self.clock.hook = failure
                self.assertEqual(self.supervise(), 1)
                self.assertLess(self.clock.value, 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
