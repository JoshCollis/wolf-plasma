#!/usr/bin/env python3
"""CPU-only application create-payload/transport checks; no Docker or GPU use."""
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import unittest
from unittest import mock

import production_policy as policy

ROOT = Path(__file__).resolve().parents[1]
MASKS = ['/sys/firmware', '/sys/devices/virtual/powercap']
CAPS = ['SYS_ADMIN', 'SYS_NICE', 'SYS_PTRACE', 'NET_RAW', 'MKNOD', 'NET_ADMIN']
SECURITY = ['seccomp=unconfined', 'apparmor=unconfined', 'label=disable']


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tests' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ApplicationPolicyTests(unittest.TestCase):
    def assert_policy(self, host):
        self.assertIs(host['Privileged'], False)
        self.assertEqual(host['CapAdd'], CAPS)
        self.assertEqual(host['SecurityOpt'], SECURITY)
        self.assertEqual(host['MaskedPaths'], MASKS)
        self.assertEqual(host['ReadonlyPaths'], [])
        self.assertFalse(any(path.startswith('/proc') for path in host['MaskedPaths']))
        self.assertNotIn('systempaths=unconfined', host['SecurityOpt'])
        self.assertEqual(host['ShmSize'], 1024**3)

    def test_complete_existing_policy_and_fresh_arrays(self):
        host = policy.application_host_config()
        self.assert_policy(host)
        host['MaskedPaths'].clear()
        self.assert_policy(policy.application_host_config())

    def test_browser_payload_preserves_limits_devices_and_private_home(self):
        config = load('browser-run').browser_config('sha256:fixture', 'new-owned-home', '5:135')
        host = config['HostConfig']
        self.assert_policy(host)
        self.assertEqual((host['NetworkMode'], host['Memory'], host['NanoCpus']), ('none', 3 * 1024**3, 3_000_000_000))
        self.assertEqual(host['Devices'], [{'PathOnHost':'/dev/udmabuf', 'PathInContainer':'/dev/udmabuf', 'CgroupPermissions':'rw'}])
        self.assertEqual(host['Binds'], ['new-owned-home:/home/retro', f'{ROOT / "tests"}:/tests:ro'])
        self.assertIn('GOW_REQUIRED_DEVICES=/dev/udmabuf', config['Env'])

    def test_flatpak_uses_same_policy_and_real_proc_namespace_prerequisite(self):
        config = load('sandbox-run').sandbox_config('sha256:fixture')
        self.assert_policy(config['HostConfig'])
        self.assertEqual(config['HostConfig']['NetworkMode'], 'bridge')
        self.assertIn('unshare -Urmpf --mount-proc true', config['Cmd'][0])

    def test_payload_construction_has_no_external_actions_or_sandbox_bypass(self):
        with mock.patch('subprocess.run', side_effect=AssertionError('external command')), \
             mock.patch.object(socket.socket, 'connect', side_effect=AssertionError('socket access')), \
             mock.patch('os.chmod', side_effect=AssertionError('host chmod')), \
             mock.patch('os.chown', side_effect=AssertionError('host chown')):
            configs = [load('browser-run').browser_config('fixture', 'owned-home', '5:135'),
                       load('sandbox-run').sandbox_config('fixture')]
        for config in configs:
            text = json.dumps(config)
            for forbidden in ('--no-sandbox', 'WEBKIT_DISABLE_SANDBOX', 'systempaths=unconfined',
                              'sysctl', 'modprobe', '/var/run/docker.sock:', '--privileged'):
                self.assertNotIn(forbidden, text)
            self.assertNotIn('PidMode', config['HostConfig'])
            self.assertNotIn('PortBindings', config['HostConfig'])

    def test_engine_create_serializes_selective_masks_and_empty_readonly(self):
        config = load('browser-run').browser_config('fixture', 'owned-home', '5:135')
        engine = mock.Mock()
        version, created = mock.Mock(), mock.Mock()
        version.read.return_value = b'{"ApiVersion":"1.47"}'
        created.status, created.read.return_value = 201, b'{"Id":"owned-id"}'
        engine.getresponse.side_effect = [version, created]
        with mock.patch.object(policy, 'Engine', return_value=engine):
            self.assertEqual(policy.create_container(config, name='owned-name', endpoint='unix:///fixture.sock'), 'owned-id')
        request = engine.request.call_args_list[1]
        self.assertEqual(request.args[:2], ('POST', '/v1.47/containers/create?name=owned-name'))
        self.assert_policy(json.loads(request.args[2])['HostConfig'])
        engine.close.assert_called_once()

    def test_default_masks_or_missing_readonly_are_rejected(self):
        for key, value in [('MaskedPaths', MASKS + ['/proc/kcore']), ('MaskedPaths', []),
                           ('ReadonlyPaths', ['/proc/sys']), ('Privileged', True)]:
            host = policy.application_host_config()
            host[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                policy.assert_path_policy(host)
        host = policy.application_host_config()
        host.pop('ReadonlyPaths')
        with self.assertRaises(RuntimeError):
            policy.assert_path_policy(host)

    def test_timeout_removes_only_exact_created_container(self):
        config = load('browser-run').browser_config('fixture', 'owned-home', '5:135')
        def run(argv, **kwargs):
            if 'start' in argv:
                raise subprocess.TimeoutExpired(argv, 1)
            return subprocess.CompletedProcess(argv, 0)
        with mock.patch.object(policy, 'create_container', return_value='owned-id'), \
             mock.patch.object(policy, 'docker_endpoint', return_value='unix:///fixture.sock'), \
             mock.patch.object(policy.subprocess, 'check_output', return_value=json.dumps(config['HostConfig'])), \
             mock.patch.object(policy.subprocess, 'run', side_effect=run) as commands:
            with self.assertRaises(subprocess.TimeoutExpired):
                policy.run_container(config, timeout=1)
        self.assertEqual(commands.call_args.args[0],
                         ['docker', '--host', 'unix:///fixture.sock', 'rm', '--force', '--volumes', 'owned-id'])

    def test_core_tests_remain_separate(self):
        source = (ROOT / 'tests/run.sh').read_text()
        core, application = source.split('# Full application sandbox gate', 1)
        self.assertNotIn('--cap-add', core)
        self.assertNotIn('production-policy.sh', core)
        self.assertIn('bash "$root/tests/production-policy.sh" "$image" "$volume"', application)


if __name__ == '__main__':
    unittest.main(verbosity=2)
