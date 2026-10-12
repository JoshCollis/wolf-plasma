#!/usr/bin/env bash
set -euo pipefail
umask "${UMASK:-022}"
if [[ $(id -u) = 0 ]]; then
    printf '%s\n' 'Plasma must run as the GoW desktop user, not root.' >&2
    exit 1
fi
# Subreaper handles orphaned session services; forward container signals to supervisor.
exec tini -s -- python3 /opt/wolf-plasma/session.py
