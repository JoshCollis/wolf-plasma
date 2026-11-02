#!/usr/bin/env bash
# Parent-only disposable GPU lab, AFTER the image's normal GoW root hooks.
set -euo pipefail
test "$(id -u)" = 0
# The driver supplies a new internal-only network. ClusterCut's local-IP probe
# needs a route, but this container cannot reach the LAN/WAN through that bridge.
if ! ip route show default | grep -q .; then ip route add default dev eth0; fi
exec gosu "$UNAME" python3 /tests/gpu-session.py
