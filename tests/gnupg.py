"""Exercise GPG agent display setup, Qt Pinentry and disposable encryption keys."""
import ctypes
import ctypes.util
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time


def run(args, env=None, data=None):
    return subprocess.check_output(args, env=env, input=data, text=True, stderr=subprocess.PIPE)


def close_window(window):
    class Data(ctypes.Union):
        _fields_ = [('l', ctypes.c_long * 5)]

    class Message(ctypes.Structure):
        _fields_ = [('type', ctypes.c_int), ('serial', ctypes.c_ulong),
                    ('send_event', ctypes.c_int), ('display', ctypes.c_void_p),
                    ('window', ctypes.c_ulong), ('message_type', ctypes.c_ulong),
                    ('format', ctypes.c_int), ('data', Data)]

    class Event(ctypes.Union):
        _fields_ = [('message', Message), ('pad', ctypes.c_long * 24)]

    x = ctypes.CDLL(ctypes.util.find_library('X11'))
    x.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x.XOpenDisplay.restype = ctypes.c_void_p
    x.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    x.XInternAtom.restype = ctypes.c_ulong
    x.XSendEvent.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long, ctypes.POINTER(Event)]
    x.XFlush.argtypes = [ctypes.c_void_p]
    x.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = x.XOpenDisplay(None)
    assert display, 'Cannot open the test X display'
    event = Event()
    event.message.type = 33
    event.message.display = display
    event.message.window = window
    event.message.message_type = x.XInternAtom(display, b'WM_PROTOCOLS', 0)
    event.message.format = 32
    event.message.data.l[0] = x.XInternAtom(display, b'WM_DELETE_WINDOW', 0)
    assert x.XSendEvent(display, window, 0, 0, ctypes.byref(event))
    x.XFlush(display)
    x.XCloseDisplay(display)


def main():
    # The ordinary agent must already have the desktop's startup display.
    info = run(['gpg-connect-agent', 'GETINFO std_startup_env', '/bye'])
    assert 'DISPLAY=' + os.environ['DISPLAY'] in info
    assert 'XAUTHORITY=' + os.environ['XAUTHORITY'] in info
    with tempfile.TemporaryDirectory(prefix='gpg-test-', dir=os.environ['XDG_RUNTIME_DIR']) as home:
        env = dict(os.environ, GNUPGHOME=home, QT_QPA_PLATFORM='xcb', KDE_FULL_SESSION='true')
        (Path(home) / 'common.conf').write_text('use-keyboxd\n')
        config = Path(home) / 'gpg-agent.conf'
        config.write_text('default-cache-ttl 90\n# user configuration\n')
        before = config.read_bytes()
        prompt = None
        try:
            run(['/opt/wolf-plasma/gpg-session.sh'], env=env)
            assert config.read_bytes() == before
            # Ask the real GPG agent to display a passphrase dialog, then cancel it.
            prompt = subprocess.Popen(
                ['gpg-connect-agent', 'GET_PASSPHRASE --data X X Test Disposable_GPG_test', '/bye'],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            window = None
            for _ in range(100):
                clients = run(['xprop', '-root', '_NET_CLIENT_LIST'])
                for wid in re.findall(r'0x[0-9a-fA-F]+', clients):
                    props = run(['xprop', '-id', wid, 'WM_CLASS'])
                    if 'pinentry' in props.lower():
                        window = int(wid, 16)
                        break
                if window:
                    break
                assert prompt.poll() is None, 'GPG prompt exited before displaying a window'
                time.sleep(.1)
            assert window, 'Graphical GPG Pinentry did not appear'
            close_window(window)
            output, _ = prompt.communicate(timeout=10)
            assert 'ERR ' in output and 'cancel' in output.lower(), output
            print('GPG agent graphical passphrase dialog opened and cancelled')
            # Keys exist only in this disposable test home and are removed on exit.
            gpg = ['gpg', '--batch', '--pinentry-mode', 'loopback', '--passphrase', '']
            run(gpg + ['--quick-generate-key', 'Desktop test <test@example.invalid>', 'ed25519', 'sign', '1d'], env=env)
            keys = run(['gpg', '--with-colons', '--list-secret-keys'], env=env)
            fingerprint = next(line.split(':')[9] for line in keys.splitlines() if line.startswith('fpr:'))
            run(gpg + ['--quick-add-key', fingerprint, 'cv25519', 'encr', '1d'], env=env)
            plaintext = Path(home) / 'message.txt'
            ciphertext = Path(home) / 'message.gpg'
            plaintext.write_text('desktop-gpg-roundtrip\n')
            run(['gpg', '--batch', '--yes', '--trust-model', 'always', '--recipient', fingerprint,
                 '--output', str(ciphertext), '--encrypt', str(plaintext)], env=env)
            assert run(gpg + ['--decrypt', str(ciphertext)], env=env) == plaintext.read_text()
            print('Disposable encryption-capable GPG key encrypt/decrypt roundtrip passed')
        finally:
            if prompt is not None and prompt.poll() is None:
                prompt.terminate()
                prompt.communicate(timeout=10)
            subprocess.run(['gpgconf', '--kill', 'all'], env=env, check=True)
    print('GPG session setup and user-configuration preservation passed')


if __name__ == '__main__':
    main()
