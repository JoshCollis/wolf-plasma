#!/usr/bin/env python3
"""Real keyboxd crash/recreation acceptance using a disposable Docker volume."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid


def command(args, **kwargs):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=60, **kwargs)


def container(mode):
    home = Path(os.environ['HOME']) / '.gnupg'
    home.mkdir(mode=0o700, exist_ok=True)
    (home / 'common.conf').write_text('use-keyboxd\n') if not (home / 'common.conf').exists() else None
    config = home / 'gpg-agent.conf'
    if not config.exists():
        config.write_text('default-cache-ttl 90\n# disposable user config\n')
    lease = None
    sys.path.insert(0, '/opt/wolf-plasma')
    if mode not in ('legacy', 'live'):
        from gpg_lifecycle import GpgLifecycle
        lease = GpgLifecycle(os.environ)
        lease.start()
    gpg = ['gpg', '--batch', '--pinentry-mode', 'loopback', '--passphrase', '']
    try:
        fingerprint = home / 'test-fingerprint'
        if not fingerprint.exists():
            command(gpg + ['--quick-generate-key', 'Crash test <crash@example.invalid>', 'ed25519', 'sign', '1d'])
            keys = command(['gpg', '--with-colons', '--list-secret-keys'])
            fpr = next(line.split(':')[9] for line in keys.splitlines() if line.startswith('fpr:'))
            command(gpg + ['--quick-add-key', fpr, 'cv25519', 'encr', '1d'])
            fingerprint.write_text(fpr)
        fpr = fingerprint.read_text()
        keys = command(['gpg', '--with-colons', '--list-secret-keys'])
        assert fpr in keys and ':e:' in keys, keys
        ciphertext = home / 'test-message.gpg'
        command(['gpg', '--batch', '--yes', '--trust-model', 'always', '-r', fpr,
                 '-o', str(ciphertext), '--encrypt'], input='keyboxd-crash-roundtrip\n')
        assert command(gpg + ['--decrypt', str(ciphertext)]).endswith('keyboxd-crash-roundtrip\n')
        before = {str(p.relative_to(home)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in [config, home / 'common.conf', *sorted((home / 'private-keys-v1.d').glob('*'))]}
        manifest = home / 'test-manifest.json'
        if manifest.exists():
            assert json.loads(manifest.read_text()) == before, 'Private keys or configuration changed'
        else:
            manifest.write_text(json.dumps(before))
        lock = home / 'public-keys.d/pubring.db.lock'
        assert lock.exists(), 'Test did not use a real keyboxd lock'
        assert os.uname().nodename.encode() in lock.read_bytes()
        if mode == 'live':
            # An unleased real local keyboxd must not be adopted or its lock removed.
            from gpg_lifecycle import GpgLifecycle
            data = lock.read_bytes()
            contender = GpgLifecycle(os.environ)
            try:
                contender.start()
            except RuntimeError as exc:
                assert 'Existing local GPG daemon' in str(exc), str(exc)
            else:
                raise AssertionError('Live keyboxd takeover accepted')
            finally:
                contender.close()
            assert lock.read_bytes() == data
            print('PASS: real unleased live keyboxd lock preserved', flush=True)
            return
        if lease:
            from gpg_lifecycle import GpgLifecycle
            data = lock.read_bytes()
            contender = GpgLifecycle(os.environ)
            try:
                contender.start()
            except RuntimeError as exc:
                assert 'Another desktop' in str(exc), str(exc)
            else:
                raise AssertionError('Competing lease accepted')
            finally:
                contender.close()
            assert lock.read_bytes() == data
        signal.signal(signal.SIGTERM, signal.SIG_IGN if mode == 'forced' else lambda *_: sys.exit(0))
        print('READY: real keyboxd encryption and unchanged private-key/config hashes', flush=True)
        while True:
            time.sleep(0.1)
    finally:
        if lease:
            lease.shutdown()
        elif mode == 'live':
            command(['gpgconf', '--kill', 'all'])


def host(image, baseline=False):
    root = Path(__file__).resolve().parent
    volume = command(['docker', 'volume', 'create']).strip()
    names = []
    entry = ('mkdir -p /run/user/1000; chmod 700 /run/user/1000; '
             'chown 1000:1000 /run/user/1000 /home/retro; '
             'exec gosu 1000:1000 env HOME=/home/retro python3 /tests/gpg-crash.py --container "$MODE"')
    def start(hostname, mode):
        name = 'wolf-gpg-test-' + uuid.uuid4().hex[:12]
        names.append(name)
        command(['docker', 'run', '-d', '--name', name, '--hostname', hostname, '--network', 'none',
                 '--entrypoint', 'bash', '-e', 'HOME=/home/retro', '-e', 'XDG_RUNTIME_DIR=/run/user/1000',
                 '-e', 'WOLF_PLASMA_GPG_ISOLATED_HOME=1', '-e', f'MODE={mode}',
                 '-v', volume + ':/home/retro', '-v', str(root) + ':/tests:ro', image, '-ec', entry])
        for _ in range(150):
            logs = command(['docker', 'logs', name])
            if 'READY:' in logs:
                return name
            if command(['docker', 'inspect', '-f', '{{.State.Running}}', name]).strip() != 'true':
                raise AssertionError(logs)
            time.sleep(.1)
        raise AssertionError(command(['docker', 'logs', name]))
    try:
        first = start('keybox-crash-a', 'legacy' if baseline else 'managed')
        if not baseline:
            read_lock = ['docker', 'exec', first, 'python3', '-c',
                         'from pathlib import Path; print(Path("/home/retro/.gnupg/public-keys.d/pubring.db.lock").read_bytes().hex())']
            before = command(read_lock)
            contender = subprocess.run(
                ['docker', 'run', '--rm', '--hostname', 'keybox-competing-session', '--network', 'none',
                 '--entrypoint', 'bash', '-e', 'HOME=/home/retro', '-e', 'XDG_RUNTIME_DIR=/run/user/1000',
                 '-e', 'WOLF_PLASMA_GPG_ISOLATED_HOME=1', '-e', 'MODE=managed',
                 '-v', volume + ':/home/retro', '-v', str(root) + ':/tests:ro', image, '-ec', entry],
                text=True, capture_output=True, timeout=30)
            assert contender.returncode != 0 and 'Another desktop session' in contender.stderr, contender.stderr
            assert command(read_lock) == before, 'Competing container altered live keyboxd lock'
            print('PASS: simultaneous different-hostname container refused; live lock bytes unchanged')
        command(['docker', 'kill', '--signal', 'KILL', first])
        assert command(['docker', 'inspect', '-f', '{{.State.ExitCode}}', first]).strip() == '137'
        if baseline:
            # Old session display setup cannot repair the foreign-host lock.
            probe = subprocess.run(['docker', 'run', '--rm', '--hostname', 'keybox-crash-b', '--network', 'none',
                                    '--entrypoint', 'bash', '-e', 'HOME=/home/retro', '-v', volume + ':/home/retro',
                                    image, '-ec', 'gosu 1000:1000 env HOME=/home/retro /opt/wolf-plasma/gpg-session.sh; '
                                    'gosu 1000:1000 env HOME=/home/retro timeout 5 gpg --list-secret-keys'],
                                   text=True, capture_output=True, timeout=30)
            assert probe.returncode == 0, f'Foreign-host keyboxd lock blocks listing (rc={probe.returncode}): {probe.stderr}'
            return
        second = start('keybox-crash-b', 'forced')
        assert 'Recovered isolated' in command(['docker', 'logs', second])
        command(['docker', 'stop', '-t', '0', second])
        assert command(['docker', 'inspect', '-f', '{{.State.ExitCode}}', second]).strip() == '137'
        third = start('keybox-crash-c', 'managed')
        assert 'Recovered isolated' in command(['docker', 'logs', third])
        command(['docker', 'stop', '-t', '15', third])
        assert command(['docker', 'inspect', '-f', '{{.State.ExitCode}}', third]).strip() == '0'
        result = command(['docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'bash',
                          '-v', volume + ':/home/retro', image, '-ec',
                          'test ! -e /home/retro/.gnupg/public-keys.d/pubring.db.lock; '
                          'test -e /home/retro/.gnupg/.wolf-plasma-lifecycle.lock; echo clean-shutdown-passed'])
        print(result.strip())
        print(command(['docker', 'run', '--rm', '--hostname', 'keybox-live-check', '--network', 'none',
                       '--entrypoint', 'bash', '-e', 'HOME=/home/retro',
                       '-e', 'XDG_RUNTIME_DIR=/run/user/1000', '-e', 'WOLF_PLASMA_GPG_ISOLATED_HOME=1',
                       '-e', 'MODE=live', '-v', volume + ':/home/retro',
                       '-v', str(root) + ':/tests:ro', image, '-ec', entry]).strip())
        print('PASS: two SIGKILL/recreations across three hostnames; real keyboxd, encryption, hash preservation, competing lease, graceful shutdown')
    finally:
        for name in names:
            subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, check=True)
        subprocess.run(['docker', 'volume', 'rm', volume], stdout=subprocess.DEVNULL, check=True)


if __name__ == '__main__':
    if sys.argv[1] == '--container':
        container(sys.argv[2])
    else:
        host(sys.argv[1], '--baseline' in sys.argv)
