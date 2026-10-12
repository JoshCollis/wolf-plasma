#!/usr/bin/env python3
"""Safety regressions; only disposable homes, no real user GPG state."""
import importlib.util
import os
from pathlib import Path
import socket
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'overlay/opt/wolf-plasma/gpg_lifecycle.py'
if not SOURCE.exists():
    SOURCE = Path('/opt/wolf-plasma/gpg_lifecycle.py')


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SOURCE.exists(), 'Session lifecycle lease/recovery is missing')
        spec = importlib.util.spec_from_file_location('gpg_lifecycle', SOURCE)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory(prefix='gpg-lifecycle-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.gpg = self.home / '.gnupg'
        self.gpg.mkdir(mode=0o700)
        self.public = self.gpg / 'public-keys.d'
        self.public.mkdir(mode=0o700)
        (self.public / 'pubring.db').write_bytes(b'preserve database')
        self.lock = self.public / 'pubring.db.lock'
        self.env = {'HOME': str(self.home), 'WOLF_PLASMA_GPG_ISOLATED_HOME': '1'}

    def owner(self, pid=2147483647, host='removed-container'):
        return f'{pid:10d}\n{host}\n'.encode()

    def start(self):
        lease = self.module.GpgLifecycle(self.env)
        self.addCleanup(lease.close)
        lease.start()
        return lease

    def test_recovers_foreign_hostname_lock_without_touching_database_or_keys(self):
        for name in ('pubring.db', 'private-keys-v1.d', 'gpg.conf', 'common.conf'):
            (self.gpg / name).write_bytes(b'preserve')
        self.lock.write_bytes(self.owner())
        self.public.chmod(0o750)  # GnuPG's real directory mode under umask 022.
        companion = self.public / '.#lk0x00001234.removed-container.2147483647'
        os.link(self.lock, companion)  # Real GnuPG dotlocks have two links.
        self.start()
        self.assertFalse(self.lock.exists())
        self.assertEqual(companion.read_bytes(), self.owner())
        for name in ('pubring.db', 'private-keys-v1.d', 'gpg.conf', 'common.conf'):
            self.assertEqual((self.gpg / name).read_bytes(), b'preserve')

    def test_refuses_foreign_lock_without_isolation_assertion(self):
        self.env.pop('WOLF_PLASMA_GPG_ISOLATED_HOME')
        self.lock.write_bytes(self.owner())
        with self.assertRaises(RuntimeError):
            self.start()
        self.assertEqual(self.lock.read_bytes(), self.owner())

    def test_live_pid_lock_is_preserved(self):
        data = self.owner(os.getpid(), socket.gethostname())
        self.lock.write_bytes(data)
        with self.assertRaises(RuntimeError):
            self.start()
        self.assertEqual(self.lock.read_bytes(), data)

    def test_competing_session_cannot_remove_lock(self):
        self.start()
        self.lock.write_bytes(self.owner())
        with self.assertRaises(RuntimeError):
            self.start()
        self.assertTrue(self.lock.exists())

    def test_custom_home_is_not_managed_or_changed(self):
        custom = self.home / 'custom'
        custom.mkdir()
        config = custom / 'gpg-agent.conf'
        config.write_bytes(b'user custom config')
        self.env['GNUPGHOME'] = str(custom)
        self.lock.write_bytes(self.owner())
        lease = self.start()
        self.assertFalse(lease.managed)
        self.assertEqual(config.read_bytes(), b'user custom config')
        self.assertTrue(self.lock.exists())
        self.assertFalse((custom / '.wolf-plasma-lifecycle.lock').exists())

    def test_malformed_symlink_hardlink_and_unsafe_permissions_are_refused(self):
        target = self.home / 'target'
        target.write_bytes(self.owner())
        for kind in ('malformed', 'symlink', 'hardlink', 'writable'):
            with self.subTest(kind=kind):
                if kind == 'symlink':
                    self.lock.symlink_to(target)
                elif kind == 'hardlink':
                    os.link(target, self.lock)
                else:
                    self.lock.write_bytes(b'bad\n' if kind == 'malformed' else self.owner())
                    if kind == 'writable':
                        self.lock.chmod(0o666)
                with self.assertRaises(RuntimeError):
                    self.start()
                self.assertTrue(self.lock.is_symlink() or self.lock.exists())
                self.lock.unlink()
        self.assertEqual(target.read_bytes(), self.owner())

    def test_symlink_gnupg_and_public_directory_refused(self):
        (self.public / 'pubring.db').unlink()
        self.public.rmdir()
        target = self.home / 'other'
        target.mkdir(mode=0o700)
        self.public.symlink_to(target, target_is_directory=True)
        with self.assertRaises(RuntimeError):
            self.start()
        self.public.unlink()
        (self.gpg / '.wolf-plasma-lifecycle.lock').unlink(missing_ok=True)
        self.gpg.rmdir()
        self.gpg.symlink_to(target, target_is_directory=True)
        with self.assertRaises(RuntimeError):
            self.start()

    def test_symlink_database_is_not_recovered(self):
        target = self.home / 'database-target'
        target.write_bytes(b'database must survive')
        database = self.public / 'pubring.db'
        database.unlink()
        database.symlink_to(target)
        self.lock.write_bytes(self.owner())
        with self.assertRaises(RuntimeError):
            self.start()
        self.assertTrue(self.lock.exists())
        self.assertEqual(target.read_bytes(), b'database must survive')

    def test_symlink_or_hardlinked_lease_is_refused(self):
        target = self.home / 'lease-target'
        target.write_bytes(b'do not touch')
        path = self.gpg / '.wolf-plasma-lifecycle.lock'
        for kind in ('symlink', 'hardlink'):
            if kind == 'symlink':
                path.symlink_to(target)
            else:
                os.link(target, path)
            self.lock.write_bytes(self.owner())
            with self.assertRaises(RuntimeError):
                self.start()
            self.assertTrue(self.lock.exists())
            self.assertEqual(target.read_bytes(), b'do not touch')
            path.unlink()

    def test_changed_lock_content_is_not_removed(self):
        self.lock.write_bytes(self.owner())
        original = self.module.live_daemons
        calls = 0
        def change():
            nonlocal calls
            calls += 1
            if calls == 2:
                self.lock.write_bytes(self.owner(host='replacement'))
            return original()
        self.module.live_daemons = change
        with self.assertRaises(RuntimeError):
            self.start()
        self.assertEqual(self.lock.read_bytes(), self.owner(host='replacement'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
