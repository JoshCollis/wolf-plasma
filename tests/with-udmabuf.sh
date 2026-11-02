#!/usr/bin/env bash
# TEST ONLY, after normal GoW root init. Docker --device creates a private node.
set -euo pipefail
test "$(id -u)" = 0
test -c /dev/udmabuf
: "${WOLF_PLASMA_TEST_HOST_UDMABUF_ID:?Missing host-device identity guard}"
test "$(stat -Lc '%d:%i' /dev/udmabuf)" != "$WOLF_PLASMA_TEST_HOST_UDMABUF_ID"
# GOW_REQUIRED_DEVICES lets the inherited GoW hook add the numeric device group.
# Neither the host node nor its clone needs chmod/chown. Verify real UID access.
gosu "$UNAME" python3 -c 'import os; fd = os.open("/dev/udmabuf", os.O_RDWR); os.close(fd)'
exec gosu "$UNAME" "$@"
