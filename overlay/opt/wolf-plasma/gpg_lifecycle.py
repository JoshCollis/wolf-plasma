"""Exclusive desktop GPG lifecycle, not a general/shared-home lock repair tool.

Removal requires an operator assertion of a local, isolated, per-profile home.
flock coordinates this image's sessions ONLY; it cannot exclude older images,
other PID namespaces or remote clients. Never opt in on a shared home.
"""
import fcntl
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import time


DAEMONS = {'keyboxd', 'gpg-agent', 'scdaemon', 'dirmngr'}


def live_daemons():
    """Fail closed if same-UID process inspection is unavailable."""
    found = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            state = (entry / 'stat').read_text().rsplit(')', 1)[1].split()[0]
            if state != 'Z' and (entry / 'comm').read_text().strip() in DAEMONS:
                found.append(entry.name)
        except FileNotFoundError:
            continue
        except (OSError, IndexError) as exc:
            raise RuntimeError('Cannot inspect local GPG daemons safely') from exc
    return found


def safe_file(info):
    return (stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and info.st_nlink == 1 and not info.st_mode & 0o022)


class GpgLifecycle:
    def __init__(self, env):
        self.env = env.copy()
        self.home = Path(env['HOME']) / '.gnupg'
        # Custom GNUPGHOME is wholly user-managed, even if it aliases the default.
        self.managed = not bool(env.get('GNUPGHOME'))
        self.directory = None
        self.lease = None
        self.started = False

    def start(self):
        if not self.managed:
            return
        try:
            self._start()
        except OSError as exc:
            self.close()
            raise RuntimeError('Unsafe/unavailable GPG lifecycle paths') from exc
        except Exception:
            self.close()
            raise

    def _start(self):
        if not self.home.is_absolute():
            raise RuntimeError('HOME must be absolute for GPG lifecycle management')
        # Open each path component without following symlinks. Ancestors may be
        # root-owned but must not be writable by another user (no /tmp homes).
        directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        private_ancestor = False
        try:
            for index, part in enumerate(self.home.parts[1:]):
                if part in ('.', '..'):
                    raise RuntimeError('Noncanonical HOME is not supported')
                if index == len(self.home.parts) - 2:
                    try:
                        os.mkdir(part, 0o700, dir_fd=directory)
                    except FileExistsError:
                        pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=directory)
                os.close(directory)
                directory = child
                info = os.fstat(directory)
                if info.st_uid not in (0, os.getuid()) or (not private_ancestor and info.st_mode & 0o022):
                    raise RuntimeError('GPG home ancestors must not be externally writable')
                if info.st_uid == os.getuid() and not info.st_mode & 0o077:
                    private_ancestor = True
            info = os.fstat(directory)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise RuntimeError('Default GPG home must be owned by desktop UID, mode 0700')
            self.directory, directory = directory, None
        finally:
            if directory is not None:
                os.close(directory)
        self.lease = os.open('.wolf-plasma-lifecycle.lock',
                             os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600,
                             dir_fd=self.directory)
        if not safe_file(os.fstat(self.lease)):
            raise RuntimeError('Unsafe GPG lifecycle lease file')
        try:
            fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another desktop session owns this GPG home') from exc
        # No adoption of an already running daemon: cannot safely own its exit.
        if live_daemons():
            raise RuntimeError('Existing local GPG daemon; refusing lifecycle takeover')
        self._recover()
        self.started = True

    def _recover(self):
        try:
            public = os.open('public-keys.d', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                             dir_fd=self.directory)
        except FileNotFoundError:
            return
        try:
            info = os.fstat(public)
            if info.st_uid != os.getuid() or info.st_mode & 0o022:
                raise RuntimeError('Unsafe public key directory')
            try:
                lock = os.open('pubring.db.lock', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                               dir_fd=public)
            except FileNotFoundError:
                return
            try:
                database = os.stat('pubring.db', dir_fd=public, follow_symlinks=False)
                if not safe_file(database):
                    raise RuntimeError('Unsafe keyboxd database path; no recovery')
                original = os.fstat(lock)
                if (not stat.S_ISREG(original.st_mode) or original.st_uid != os.getuid()
                        or original.st_mode & 0o022 or original.st_nlink not in (1, 2)):
                    raise RuntimeError('Unsafe keyboxd lock file')
                owner = os.read(lock, 512)
                match = re.fullmatch(rb'([ 0-9]{10})\n([A-Za-z0-9][A-Za-z0-9_.-]{0,254})\n', owner)
                if not match or not match[1].strip().isdigit() or int(match[1]) <= 0:
                    raise RuntimeError('Malformed keyboxd lock; manual inspection required')
                pid = int(match[1])
                if original.st_nlink == 2:
                    # GnuPG creates a dotlock by linking its private .#lk file.
                    # Accept ONLY that exact, local-directory companion inode.
                    pattern = re.compile(r'\.#lk0x[0-9a-fA-F]+\.' +
                                         re.escape(match[2].decode('ascii')) + r'\.' + str(pid))
                    companions = [name for name in os.listdir(public) if pattern.fullmatch(name)]
                    if len(companions) != 1:
                        raise RuntimeError('Unknown keyboxd lock hardlink')
                    companion = os.stat(companions[0], dir_fd=public, follow_symlinks=False)
                    if (companion.st_dev, companion.st_ino) != (original.st_dev, original.st_ino):
                        raise RuntimeError('Unknown keyboxd lock hardlink')
                if match[2].decode('ascii') == socket.gethostname() and Path(f'/proc/{pid}').exists():
                    raise RuntimeError('Keyboxd lock has a live local owner')
                if self.env.get('WOLF_PLASMA_GPG_ISOLATED_HOME') != '1':
                    raise RuntimeError('Stale/foreign keyboxd lock: isolated-home assertion required; '
                                       'see README before enabling recovery')
                if live_daemons():
                    raise RuntimeError('Local GPG daemon appeared during recovery')
                # Verify pinned directories, inode, ownership/mode and owner bytes
                # immediately before removing ONLY this lock. The isolation
                # contract excludes uncooperative concurrent writers; no POSIX
                # unlink API provides a compare-and-swap against such writers.
                current = os.stat('pubring.db.lock', dir_fd=public, follow_symlinks=False)
                pub_now = os.stat('public-keys.d', dir_fd=self.directory, follow_symlinks=False)
                home_now = self.home.lstat()
                lease_now = os.stat('.wolf-plasma-lifecycle.lock', dir_fd=self.directory,
                                    follow_symlinks=False)
                db_now = os.stat('pubring.db', dir_fd=public, follow_symlinks=False)
                os.lseek(lock, 0, os.SEEK_SET)
                fields = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid',
                          'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
                if (any(getattr(current, f) != getattr(original, f) for f in fields)
                        or os.read(lock, 512) != owner
                        or not safe_file(lease_now)
                        or (lease_now.st_dev, lease_now.st_ino) !=
                           (os.fstat(self.lease).st_dev, os.fstat(self.lease).st_ino)
                        or db_now != database
                        or (pub_now.st_dev, pub_now.st_ino) != (info.st_dev, info.st_ino)
                        or (home_now.st_dev, home_now.st_ino) !=
                           (os.fstat(self.directory).st_dev, os.fstat(self.directory).st_ino)):
                    raise RuntimeError('Keyboxd lock/path changed during recovery')
                os.unlink('pubring.db.lock', dir_fd=public)
                print('Recovered isolated default-home stale keyboxd lock', flush=True)
            finally:
                os.close(lock)
        finally:
            os.close(public)

    def shutdown(self):
        """Call only after desktop clients have exited, while still holding lease."""
        try:
            if self.started:
                subprocess.run(['gpgconf', '--homedir', str(self.home), '--kill', 'all'],
                               env=self.env, check=True, timeout=5)
                deadline = time.monotonic() + 3
                while live_daemons():
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Local GPG daemon did not finish shutdown')
                    time.sleep(0.05)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            print(f'GPG daemon shutdown failed (no lock deletion; next startup checks again): {exc}',
                  flush=True)
        finally:
            self.started = False
            self.close()

    def close(self):
        # Never unlink the lease: waiters must always lock the same inode.
        for name in ('lease', 'directory'):
            fd = getattr(self, name)
            if fd is not None:
                os.close(fd)
                setattr(self, name, None)
