#!/usr/bin/env python3
"""Network-enabled disposable test with the exact example's Docker proc policy.

Uses the local Docker Engine socket only from this host-side test harness;
the socket is never mounted into the desktop. Requires Python 3.11+.
"""
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tomllib

root = Path(__file__).resolve().parents[1]
endpoint = os.environ.get("DOCKER_HOST", "unix:///var/run/docker.sock")
if not endpoint.startswith("unix://"):
    raise SystemExit("This isolated test supports only a local unix Docker endpoint")


class Engine(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(30)
        self.sock.connect(endpoint.removeprefix("unix://"))


engine = Engine("localhost")
engine.request("GET", "/version")
response = engine.getresponse()
version = json.loads(response.read())["ApiVersion"]
runner = tomllib.loads((root / "examples/wolf-plasma.toml").read_text())["apps"][0]["runner"]
config = json.loads(runner["base_create_json"])
config["HostConfig"]["Binds"] = [f"{root / 'tests'}:/tests:ro"]
config.update(Image=sys.argv[1] if len(sys.argv) > 1 else "wolf-plasma:local",
              Cmd=['exec gosu "$UNAME" dbus-run-session -- bash -e -c '
                   '"wolf-plasma-brave; bash /tests/sandbox.sh"'],
              AttachStdout=True, AttachStderr=True)
engine.request("POST", f"/v{version}/containers/create", json.dumps(config),
               {"Content-Type": "application/json"})
response = engine.getresponse()
body = response.read()
if response.status != 201:
    raise SystemExit(body.decode())
container = json.loads(body)["Id"]
try:
    subprocess.run(["docker", "start", "--attach", container], check=False, timeout=2100)
    code = subprocess.check_output(["docker", "inspect", "--format", "{{.State.ExitCode}}", container], text=True)
    raise SystemExit(int(code))
finally:
    subprocess.run(["docker", "rm", "--force", "--volumes", container], check=True,
                   stdout=subprocess.DEVNULL)
