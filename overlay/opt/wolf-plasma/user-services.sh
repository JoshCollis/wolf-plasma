#!/usr/bin/env bash
set -euo pipefail
# Run only after the packaged wrapper has published the client's own socket.
/opt/wolf-plasma/gpg-session.sh
exec /usr/local/bin/wolf-plasma-brave --background
