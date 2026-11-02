#!/usr/bin/env bash
# CLI flags cannot express the existing selective masks/empty readonly paths.
# The host-side Engine API driver sends the complete policy; no host changes.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
exec python3 "$root/tests/browser-run.py" "$@"
