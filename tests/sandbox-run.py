#!/usr/bin/env python3
"""Network-enabled disposable test with the exact example's Docker proc policy.

Uses the local Docker Engine socket only from this host-side test harness;
the socket is never mounted into the desktop. Requires Python 3.11+.
"""
from pathlib import Path
import sys
from production_policy import application_config, run_container

root = Path(__file__).resolve().parents[1]


def sandbox_config(image):
    return application_config(image, ['exec gosu "$UNAME" dbus-run-session -- bash -e -c '
        '"unshare -Urmpf --mount-proc true; wolf-plasma-brave; bash /tests/sandbox.sh"'],
        network='bridge', binds=[f"{root / 'tests'}:/tests:ro"])


if __name__ == '__main__':
    image = sys.argv[1] if len(sys.argv) > 1 else 'wolf-plasma:local'
    raise SystemExit(run_container(sandbox_config(image), timeout=2100))
