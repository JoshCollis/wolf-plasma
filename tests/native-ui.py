#!/usr/bin/env python3
"""Real native Qt/GTK pixels, portal access and graphical GPG cancellation."""
import os
from pathlib import Path
import subprocess
import sys
import time
import tempfile

from native_tools import screenshot, windows, script
from native_audio import verify as verify_audio


def gtk_window():
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk, Gdk
    app = Gtk.Application(application_id='org.wolfplasma.NativeGtkTest')
    def activate(application):
        window = Gtk.ApplicationWindow(application=application, title='Native GTK pixel proof')
        window.set_default_size(480, 320)
        box = Gtk.Box()
        provider = Gtk.CssProvider()
        provider.load_from_string('.red {background:rgb(238,34,51);} '
                                  '.green {background:rgb(24,204,102);} '
                                  '.blue {background:rgb(35,68,238);}')
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, 800)
        for color in ('red', 'green', 'blue'):
            label = Gtk.Label(label=color, hexpand=True, vexpand=True)
            label.add_css_class(color)
            box.append(label)
        window.set_child(box)
        window.present()
    app.connect('activate', activate)
    app.run(None)


def main():
    assert os.environ['XDG_SESSION_TYPE'] == 'wayland'
    assert os.environ['QT_QPA_PLATFORM'] == 'wayland'
    assert not os.environ.get('DISPLAY')
    processes = []
    try:
        qt = subprocess.Popen(['konsole', '--separate', '--title', 'Native Qt proof',
                               '-e', 'bash', '-c', 'printf "Native Qt Wayland acceptance\\n"; sleep 60'])
        processes.append(qt)
        gtk = subprocess.Popen([sys.executable, __file__, '--gtk'])
        processes.append(gtk)
        for _ in range(100):
            clients = windows()
            if any(window['pid'] == qt.pid for window in clients) and any(window['pid'] == gtk.pid for window in clients):
                break
            time.sleep(.1)
        else:
            raise AssertionError(f'Real native Qt and GTK windows missing: {clients}')
        assert script(f'const w = workspace.windowList().find(w => w.pid === {gtk.pid}); '
                      'w.minimized=false; w.keepAbove=true; workspace.activeWindow=w; return true;')
        for _ in range(10):
            time.sleep(.3)
            info, pixels = screenshot()
            assert info['width'] == 800 and info['height'] == 600, info
            counts = [0, 0, 0]
            assert info['format'] in (4, 5, 6, 16, 17, 18), info
            for offset in range(0, len(pixels), 4):
                rgb = pixels[offset:offset + 3]
                if info['format'] in (4, 5, 6):
                    rgb = rgb[::-1]
                for index, color in enumerate(((238, 34, 51), (24, 204, 102), (35, 68, 238))):
                    if all(abs(a-b) < 12 for a, b in zip(rgb, color)):
                        counts[index] += 1
            if min(counts) > 500:
                break
        else:
            raise AssertionError(f'Native compositor pixels absent after warmup: {counts}; {windows()}')
        assert script(f'const w = workspace.windowList().find(w => w.pid === {gtk.pid}); '
                      'w.keepAbove=false; w.minimized=true; return true;')
        print(f'PASS: real native Qt/GTK windows and compositor screenshot pixels {counts}', flush=True)
        portal = subprocess.check_output(['gdbus', 'call', '--session', '--dest', 'org.freedesktop.portal.Desktop',
                        '--object-path', '/org/freedesktop/portal/desktop', '--method',
                        'org.freedesktop.portal.Settings.Read', 'org.freedesktop.appearance', 'color-scheme'],
                       text=True, timeout=15)
        assert 'uint32 1' in portal, portal
        verify_audio(dict(os.environ))
        subprocess.run([sys.executable, '/tests/gnupg.py'], check=True, timeout=45)
        if os.environ.get('NATIVE_BROWSER_GATE') == '1':
            with tempfile.TemporaryFile(mode='w+') as log:
                browser = subprocess.Popen([sys.executable, '/tests/native-browser.py'], stdout=log, stderr=log)
                processes.append(browser)
                for _ in range(150):
                    status = browser.poll()
                    log.seek(0)
                    output = log.read()
                    assert status is None, f'Native sandboxed browser exited ({status}): {output}'
                    if 'NATIVE_WEBKIT_LOAD_FINISHED' in output:
                        break
                    time.sleep(.1)
                else:
                    raise AssertionError(f'Native sandboxed browser failed to render: {output}')
                assert script(f'const w=workspace.windowList().find(w=>w.pid==={browser.pid}); '
                              'if(w){w.minimized=false;w.keepAbove=true;workspace.activeWindow=w;} return !!w;')
                time.sleep(.5)
                info, pixels = screenshot()
                colors = [pixels[offset:offset+3] for offset in range(0, len(pixels), 4)]
                if info['format'] in (4, 5, 6):
                    colors = [color[::-1] for color in colors]
                count = sum(all(abs(a-b) < 12 for a, b in zip(color, (44, 126, 230))) for color in colors)
                assert count > 500, f'No native WebKit browser pixels: {count}'
                print(f'PASS: native sandboxed WebKit browser pixels {count}', flush=True)
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)


if __name__ == '__main__':
    gtk_window() if '--gtk' in sys.argv else main()
