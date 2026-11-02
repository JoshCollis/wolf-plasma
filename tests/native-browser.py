#!/usr/bin/env python3
"""Native WebKit browser acceptance; never disables the browser sandbox."""
import gi
import os
assert os.environ.get('WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS') not in ('1', 'true'), 'Sandbox-disable environment is forbidden'
gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gtk, WebKit2

context = WebKit2.WebContext.get_default()
# GTK3's 4.1 API requires opting in; the GTK4/6.0 API makes this mandatory.
context.set_sandbox_enabled(True)
assert context.get_sandbox_enabled(), 'WebKit sandbox must remain enabled'
window = Gtk.Window(title='Native sandboxed WebKit proof')
window.set_default_size(500, 340)
view = WebKit2.WebView(web_context=context)
view.connect('load-changed', lambda view, event: print('NATIVE_WEBKIT_LOAD_FINISHED', flush=True)
             if event == WebKit2.LoadEvent.FINISHED else None)
view.connect('web-process-terminated', lambda view, reason: print(f'NATIVE_WEBKIT_CRASH {reason}', flush=True))
view.load_html('<!doctype html><title>Native WebKit acceptance</title>'
               '<body style="margin:0;background:rgb(44,126,230);color:white">'
               'Native sandboxed WebKit browser</body>', 'about:blank')
window.add(view)
window.connect('destroy', Gtk.main_quit)
window.show_all()
Gtk.main()
