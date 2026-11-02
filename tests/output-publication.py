#!/usr/bin/env python3
"""Real readiness-function regressions for learned backend vs stale wl_output."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / 'overlay/opt/wolf-plasma/session.py'
if not SOURCE.exists():
    SOURCE = Path('/opt/wolf-plasma/session.py')
sys.path.insert(0, str(SOURCE.parent))
spec = importlib.util.spec_from_file_location('publication_session_test', SOURCE)
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mode-publication-')
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        (self.state / 'compositor.json').write_text(json.dumps({'pid':os.getpid(), 'socket':'child'}))
        (self.state / 'bus').write_text('unix:path=/private-child-bus')
        self.env = {'XDG_RUNTIME_DIR':str(self.state), 'WAYLAND_DISPLAY':'/private-wolf/parent',
                    'WOLF_PLASMA_PARENT_DISPLAY':'/private-wolf/parent', 'QT_QPA_PLATFORM':'wayland'}
        self.output = {'id':1, 'name':'WL-0', 'connected':True, 'currentModeId':'1',
            'modes':[{'id':'1','refreshRate':90.0,'size':{'width':800,'height':600}}]}
        self.queries, self.applies = 0, 0
        self.keep_stale, self.query_timeout, self.bad_json = False, False, False
        self.apply_timeout, self.apply_error = False, False
        self.extra_outputs = []

    def modes(self, path):
        self.assertEqual(path, str(self.state / 'child'))
        return [{'width':800,'height':600,
                 'refresh_mHz':90000 if self.applies and not self.keep_stale else 60000}]

    def ipc(self, argv, **kwargs):
        if argv[0] == 'dbus-send':
            return subprocess.CompletedProcess(argv,0,'variant boolean true','')
        if argv[0] == 'pgrep':
            return subprocess.CompletedProcess(argv,0)
        self.assertEqual(argv[0], 'kscreen-doctor')
        self.assertEqual(kwargs['env']['WAYLAND_DISPLAY'], str(self.state / 'child'))
        self.assertEqual(kwargs['env']['DBUS_SESSION_BUS_ADDRESS'], 'unix:path=/private-child-bus')
        self.assertLessEqual(kwargs['timeout'], 2)
        if argv == ['kscreen-doctor','-j']:
            self.queries += 1
            if self.query_timeout:
                raise subprocess.TimeoutExpired(argv,2)
            return subprocess.CompletedProcess(argv,0,'{' if self.bad_json else json.dumps(
                {'outputs':[self.output, *self.extra_outputs]}),'')
        self.assertEqual(argv, ['kscreen-doctor','output.1.mode.1'])
        self.applies += 1
        if self.apply_timeout:
            raise subprocess.TimeoutExpired(argv,2)
        return subprocess.CompletedProcess(argv,1 if self.apply_error else 0,'','')

    def ready(self, **kwargs):
        with mock.patch.object(session,'parent_modes',self.modes), \
             mock.patch.object(session.subprocess,'run',self.ipc):
            return session.native_ready(self.state,self.env,800,600,90,**kwargs)

    def test_actual_current_90_is_republished_without_creating_or_forcing_a_mode(self):
        self.assertTrue(self.ready())
        self.assertEqual((self.queries,self.applies),(1,1))

    def test_backend_still_60_cannot_be_relabelled_90(self):
        self.output['modes'][0]['refreshRate'] = 60.0
        self.assertFalse(self.ready())
        self.assertEqual((self.queries,self.applies),(1,0))

    def test_available_90_is_not_used_when_current_backend_mode_is_60(self):
        self.output['currentModeId'] = '0'
        self.output['modes'].append({'id':'0','refreshRate':60.0,'size':{'width':800,'height':600}})
        self.assertFalse(self.ready())
        self.assertEqual((self.queries,self.applies),(1,0))

    def test_wrong_backend_size_and_foreign_parent_output_are_not_reconfigured(self):
        for field,value in [('size',{'width':1280,'height':720}),('name','HEADLESS-1')]:
            with self.subTest(field=field):
                if field == 'size':
                    self.output['modes'][0]['size'] = value
                else:
                    self.output['modes'][0]['size'] = {'width':800,'height':600}
                    self.output['name'] = value
                self.queries = 0
                self.assertFalse(self.ready())
                self.assertEqual((self.queries,self.applies),(1,0))

    def test_publication_attempt_is_bounded_and_stale_wire_still_fails(self):
        self.keep_stale = True
        self.assertFalse(self.ready())
        self.assertFalse(self.ready())
        self.assertEqual((self.queries,self.applies),(1,1))

    def test_post_readiness_health_check_cannot_reconfigure_outputs(self):
        self.assertFalse(self.ready(allow_mode_publication=False))
        self.assertEqual((self.queries,self.applies),(0,0))

    def test_query_timeout_stays_inconclusive_for_existing_probe_grace(self):
        self.query_timeout = True
        with self.assertRaises(subprocess.TimeoutExpired):
            self.ready()
        self.assertEqual(self.applies,0)

    def test_malformed_backend_data_fails_closed(self):
        self.bad_json = True
        self.assertFalse(self.ready())
        self.assertEqual((self.queries,self.applies),(1,0))

    def test_parent_display_is_never_queried_or_reconfigured(self):
        self.env['WOLF_PLASMA_PARENT_DISPLAY'] = str(self.state / 'child')
        self.assertFalse(self.ready())
        self.assertEqual((self.queries,self.applies),(0,0))

    def test_multiple_outputs_are_never_reconfigured(self):
        self.extra_outputs = [self.output]
        self.assertFalse(self.ready())
        self.assertEqual((self.queries,self.applies),(1,0))

    def test_invalid_output_identity_or_rate_fails_closed(self):
        for key,value in [('name',None),('name','WL-'),('id','1.mode.2'),
                          ('currentModeId','custom'),('connected','true')]:
            with self.subTest(key=key,value=value):
                original = self.output[key]
                self.output[key] = value
                self.assertFalse(self.ready())
                self.output[key] = original
                self.assertEqual(self.applies,0)
        for value in (None, 'nan', 'inf', 'not-a-rate'):
            with self.subTest(rate=value):
                self.output['modes'][0]['refreshRate'] = value
                self.assertFalse(self.ready())
                self.assertEqual(self.applies,0)

    def test_apply_timeout_cannot_cause_a_second_apply(self):
        self.apply_timeout = True
        self.keep_stale = True
        with self.assertRaises(subprocess.TimeoutExpired):
            self.ready()
        self.assertFalse(self.ready())
        self.assertEqual((self.queries,self.applies),(1,1))

    def test_apply_error_cannot_cause_a_second_apply(self):
        self.apply_error = True
        self.keep_stale = True
        self.assertFalse(self.ready())
        self.assertFalse(self.ready())
        self.assertEqual((self.queries,self.applies),(1,1))


if __name__ == '__main__':
    unittest.main(verbosity=2)
