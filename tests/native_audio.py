"""Synthetic private PipeWire/Pulse fixture and an actual captured PCM gate."""
import math
import os
from pathlib import Path
import signal
import select
import struct
import subprocess
import tempfile
import time


class AudioFixture:
    def __init__(self, env):
        self.directory = tempfile.TemporaryDirectory(prefix='test-audio-', dir=env['XDG_RUNTIME_DIR'])
        path = Path(self.directory.name)
        self.env = env | {'PIPEWIRE_RUNTIME_DIR': str(path), 'PULSE_RUNTIME_PATH': str(path / 'pulse'),
                          'PULSE_SERVER': 'unix:' + str(path / 'pulse/native')}
        self.children, self.logs = [], []

    def start(self):
        bus_log = tempfile.TemporaryFile()
        self.logs.append(bus_log)
        bus = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--print-address=1'],
                               stdout=subprocess.PIPE, stderr=bus_log, text=True)
        self.children.append(bus)
        assert select.select([bus.stdout], [], [], 5)[0], 'Synthetic audio bus did not start'
        self.env['DBUS_SESSION_BUS_ADDRESS'] = bus.stdout.readline().strip()
        for command in (['pipewire'], ['pipewire-pulse'], ['wireplumber']):
            log = tempfile.TemporaryFile()
            self.logs.append(log)
            self.children.append(subprocess.Popen(command, env=self.env, stdout=log, stderr=log))
        for _ in range(100):
            result = subprocess.run(['pactl', 'info'], env=self.env, capture_output=True, timeout=2)
            if result.returncode == 0:
                break
            time.sleep(.1)
        else:
            raise AssertionError('Synthetic Pulse server did not become ready')
        subprocess.run(['pactl', 'load-module', 'module-null-sink', 'sink_name=native_test',
                        'rate=48000', 'channels=1'], env=self.env, check=True,
                       stdout=subprocess.DEVNULL, timeout=5)
        for _ in range(50):
            sources = subprocess.check_output(['pactl', 'list', 'short', 'sources'], env=self.env,
                                              text=True, timeout=3)
            if 'native_test.monitor' in sources:
                break
            time.sleep(.1)
        else:
            raise AssertionError('Synthetic sink monitor was not registered')
        return self.env

    def close(self):
        for child in reversed(self.children):
            child.terminate() if child.poll() is None else None
            child.wait(timeout=5)
            if child.stdout:
                child.stdout.close()
        for log in self.logs:
            log.seek(0)
            print(log.read().decode(errors='replace'))
            log.close()
        self.directory.cleanup()


def verify(env):
    with tempfile.TemporaryFile() as captured:
        monitor = subprocess.Popen(['parec', '--raw', '--format=s16le', '--channels=1',
                                    '--rate=48000', '--latency-msec=20', '--device=native_test.monitor'], env=env,
                                   stdout=captured, stderr=subprocess.PIPE)
        try:
            time.sleep(.2)
            pcm = b''.join(struct.pack('<h', round(10000 * math.sin(2 * math.pi * 440 * n / 48000)))
                           for n in range(48000))
            subprocess.run(['pacat', '--playback', '--raw', '--format=s16le', '--channels=1',
                            '--rate=48000', '--latency-msec=20', '--device=native_test'], env=env,
                           input=pcm, check=True, timeout=10)
            time.sleep(.3)
        finally:
            monitor.send_signal(signal.SIGTERM) if monitor.poll() is None else None
            _, errors = monitor.communicate(timeout=5)
            assert monitor.returncode in (0, -signal.SIGTERM), errors.decode()
        captured.seek(0)
        data = captured.read()
        samples = struct.unpack('<' + 'h' * (len(data) // 2), data[:len(data) // 2 * 2])
        audible = [value for value in samples if abs(value) > 100]
        assert len(audible) > 24000, f'No actual monitor audio: {len(audible)} audible / {len(samples)} captured samples'
        # A black/silent negative control cannot satisfy this gate.
        assert max(samples) > 5000 and min(samples) < -5000
        print(f'PASS: synthetic Pulse playback/monitor capture, {len(audible)} audible PCM samples', flush=True)


if __name__ == '__main__':
    fixture = AudioFixture(dict(os.environ))
    try:
        verify(fixture.start())
    finally:
        fixture.close()
