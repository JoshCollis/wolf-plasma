#!/usr/bin/env python3
"""Execute the image launcher chain with recording command fixtures."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NativeLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='native-launcher-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.record = self.directory / 'commands.jsonl'
        self.env = dict(os.environ, PATH=f'{self.directory}:/usr/bin:/bin',
                        RECORD=str(self.record), WAYLAND_DISPLAY='parent-0',
                        WOLF_PLASMA_PARENT_DISPLAY='/private/parent-0',
                        WOLF_PLASMA_SESSION_STATE=str(self.directory),
                        DBUS_SESSION_BUS_ADDRESS='unix:path=/private/test-bus',
                        GAMESCOPE_WIDTH='1280', GAMESCOPE_HEIGHT='720')

    def command(self, name):
        path = self.directory / name
        path.write_text('#!/usr/bin/python3\nimport json,os,sys\n'
                        'with open(os.environ["RECORD"], "a") as f:\n'
                        ' f.write(json.dumps(sys.argv) + "\\n")\n')
        path.chmod(0o755)
        return path

    def calls(self):
        return [json.loads(line) for line in self.record.read_text().splitlines()]

    def test_desktop_executes_native_plasma(self):
        source = (ROOT / 'overlay/opt/wolf-plasma/desktop.sh').read_text()
        for name in ('seed.sh', 'gpg-session.sh', 'wolf-plasma-brave'):
            command = self.command(name)
            source = source.replace(f'/opt/wolf-plasma/{name}', str(command))
            source = source.replace(f'/usr/local/bin/{name}', str(command))
        for name in ('dbus-update-activation-environment', 'startplasma-x11',
                     'startplasma-wayland'):
            self.command(name)
        subprocess.run(['bash', '-c', source], env=self.env, check=True, timeout=5)
        names = [Path(call[0]).name for call in self.calls()]
        self.assertIn('startplasma-wayland', names)
        self.assertNotIn('startplasma-x11', names)
        activation = next(call for call in self.calls()
                          if Path(call[0]).name == 'dbus-update-activation-environment')
        self.assertIn('WAYLAND_DISPLAY', activation)
        self.assertNotIn('DISPLAY', activation)

    def test_stock_plasma_xwayland_argument_is_removed_before_packaged_wrapper(self):
        launcher = ROOT / 'overlay/usr/local/bin/kwin_wayland_wrapper'
        self.assertTrue(launcher.is_file(), 'native-only wrapper interception is missing')
        packaged = self.command('packaged-wrapper')
        source = launcher.read_text().replace('/usr/bin/kwin_wayland_wrapper', str(packaged))
        subprocess.run(['bash', '-c', source, 'kwin_wayland_wrapper', '--xwayland'],
                       env=self.env, check=True, timeout=5)
        calls = self.calls()
        self.assertEqual(len(calls), 1, 'launch the packaged wrapper exactly once')
        self.assertFalse(any(arg.startswith('--xwayland') for arg in calls[0][1:]))
        self.assertIn('/private/parent-0', calls[0])

    def test_kwin_rejects_xwayland_even_outside_supervised_session(self):
        helper = ROOT / 'overlay/usr/local/bin/kwin_wayland'
        result = subprocess.run([sys.executable, str(helper), '--xwayland'],
                                env=self.env, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Xwayland is not supported', result.stderr)

    def test_clean_compositor_exit_is_recorded_and_wrapper_retry_is_refused(self):
        packaged = self.command('packaged-kwin')
        source = (ROOT / 'overlay/usr/local/bin/kwin_wayland').read_text()
        helper = self.directory / 'kwin-helper.py'
        helper.write_text(source.replace('/usr/bin/kwin_wayland', str(packaged)))
        argv = [sys.executable, str(helper), '--wayland-fd', '7', '--socket', 'own-client-0']
        subprocess.run(argv, env=self.env, check=True, timeout=5)
        self.assertEqual((self.directory / 'compositor-exited').read_text(), '0')
        self.assertEqual(json.loads((self.directory / 'compositor.json').read_text())['socket'], 'own-client-0')
        self.assertNotEqual(subprocess.run(argv, env=self.env, timeout=5).returncode, 0)
        self.assertEqual(len(self.calls()), 1)


if __name__ == '__main__':
    unittest.main()
