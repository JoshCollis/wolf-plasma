"""Host-side application fixtures: complete existing policy, never host changes."""
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import tomllib
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]


def application_host_config():
    example = tomllib.loads((ROOT / 'examples/wolf-plasma.toml').read_text())
    host = json.loads(example['apps'][0]['runner']['base_create_json'])['HostConfig']
    # Parent verified this third option is already present in actual profiles.
    host['SecurityOpt'].append('label=disable')
    return host


def policy_metadata():
    host = application_host_config()
    return {'capabilities': host['CapAdd'], 'security_options': host['SecurityOpt'],
            'privileged': host['Privileged'], 'masked_paths': host['MaskedPaths'],
            'readonly_paths': host['ReadonlyPaths']}


def application_config(image, command, *, network, binds, env=(), devices=(),
                       cpus=2, memory=3 * 1024**3, pids_limit=None):
    host = application_host_config()
    host.update(NetworkMode=network, Binds=list(binds), Memory=memory,
                NanoCpus=int(cpus * 1_000_000_000), Devices=[
                    {'PathOnHost': path, 'PathInContainer': path, 'CgroupPermissions': 'rw'}
                    for path in devices])
    if pids_limit is not None:
        host['PidsLimit'] = pids_limit
    return {'Image': image, 'Cmd': list(command), 'Env': list(env),
            'AttachStdout': True, 'AttachStderr': True, 'HostConfig': host}


def assert_path_policy(host):
    expected = application_host_config()
    for key in ('Privileged', 'MaskedPaths', 'ReadonlyPaths'):
        if host.get(key) != expected[key]:
            raise RuntimeError('Application fixture policy differs at ' + key)


def docker_endpoint():
    endpoint = os.environ.get('DOCKER_HOST', 'unix:///var/run/docker.sock')
    if not endpoint.startswith('unix://'):
        raise RuntimeError('Application fixtures require a local unix Docker endpoint')
    return endpoint


class Engine(http.client.HTTPConnection):
    def __init__(self, endpoint):
        super().__init__('localhost', timeout=30)
        self.endpoint = endpoint

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(30)
        self.sock.connect(self.endpoint.removeprefix('unix://'))


def create_container(config, *, name=None, endpoint=None):
    assert_path_policy(config['HostConfig'])
    endpoint = endpoint or docker_endpoint()
    if not endpoint.startswith('unix://'):
        raise RuntimeError('Application fixtures require a local unix Docker endpoint')
    engine = Engine(endpoint)
    try:
        engine.request('GET', '/version')
        response = engine.getresponse()
        version = json.loads(response.read())['ApiVersion']
        query = '?' + urlencode({'name': name}) if name else ''
        engine.request('POST', f'/v{version}/containers/create{query}', json.dumps(config),
                       {'Content-Type': 'application/json'})
        response = engine.getresponse()
        body = response.read()
        if response.status != 201:
            raise RuntimeError('Application container create failed: ' + body.decode())
        return json.loads(body)['Id']
    finally:
        engine.close()


def run_container(config, *, timeout):
    endpoint = docker_endpoint()
    docker = ['docker', '--host', endpoint]
    container = create_container(config, endpoint=endpoint)
    try:
        host = json.loads(subprocess.check_output(
            [*docker, 'inspect', '--format', '{{json .HostConfig}}', container],
            text=True, timeout=15))
        assert_path_policy(host)
        subprocess.run([*docker, 'start', '--attach', container], check=False, timeout=timeout)
        return int(subprocess.check_output(
            [*docker, 'inspect', '--format', '{{.State.ExitCode}}', container], text=True, timeout=15))
    finally:
        subprocess.run([*docker, 'rm', '--force', '--volumes', container], check=True,
                       stdout=subprocess.DEVNULL, timeout=30)
