#!/usr/bin/env bash
set -euo pipefail
image=${1:-wolf-plasma:local}
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
test -c /dev/udmabuf || { printf '%s\n' 'Native CPU tests require the existing /dev/udmabuf device; no GUI tests are skipped.' >&2; exit 1; }
device_before=$(stat -Lc '%d:%i:%u:%g:%a:%t:%T' /dev/udmabuf)
device_args=(--device=/dev/udmabuf:/dev/udmabuf:rw
    -e GOW_REQUIRED_DEVICES=/dev/udmabuf
    -e "WOLF_PLASMA_TEST_HOST_UDMABUF_ID=$(stat -Lc '%d:%i' /dev/udmabuf)")
volume=''
cleanup() {
    if [[ -n $volume ]]; then docker volume rm "$volume" >/dev/null; fi
    test "$device_before" = "$(stat -Lc '%d:%i:%u:%g:%a:%t:%T' /dev/udmabuf)" || {
        printf '%s\n' 'Host udmabuf identity/permissions changed unexpectedly' >&2; exit 1;
    }
}
trap cleanup EXIT
python3 "$root/tests/refresh.py"
python3 "$root/tests/native-launcher.py"
python3 "$root/tests/supervisor.py"
python3 "$root/tests/output-publication.py"
python3 "$root/tests/application-policy.py"
docker run --rm --network none --entrypoint python3 \
    -v "$root/tests:/tests:ro" "$image" /tests/supervisor.py
docker run --rm --network none --entrypoint python3 \
    -v "$root/tests:/tests:ro" "$image" /tests/output-publication.py
docker run --rm --network none --entrypoint python3 \
    -v "$root/tests:/tests:ro" "$image" /tests/refresh.py
docker run --rm --network none --entrypoint bash \
    -v "$root/tests:/tests:ro" "$image" /tests/image.sh
docker run --rm --network none --entrypoint python3 \
    -v "$root/tests:/tests:ro" "$image" /tests/runtime.py
docker run --rm --network none --entrypoint python3 -e TMPDIR=/home/retro \
    -v "$root/tests:/tests:ro" "$image" /tests/gpg-lifecycle.py
python3 "$root/tests/gpg-crash.py" "$image"
docker run --rm --network none -v "$root/tests:/tests:ro" "$image" 'bash /tests/shell.sh'
docker run --rm --network none -v "$root/tests:/tests:ro" "$image" \
    'exec gosu "$UNAME" dbus-run-session -- bash /tests/seed-native.sh'
docker run --rm --network none --memory 3g --cpus 3 "${device_args[@]}" -v "$root/tests:/tests:ro" "$image" \
    'exec bash /tests/with-udmabuf.sh python3 /tests/native-production-path.py'
docker run --rm --network none --memory 1g --cpus 1 "${device_args[@]}" -v "$root/tests:/tests:ro" "$image" \
    'exec bash /tests/with-udmabuf.sh dbus-run-session -- bash /tests/virtual-render-gate.sh'
# Recreate with the same disposable home: verify state across container lifetime.
volume=$(docker volume create)
# Exercise the actual native nesting launcher at the formerly failing rate.
# Do not substitute virtual-wrapper.sh for the child in this regression.
docker run --rm --network none --memory 3g --cpus 3 --shm-size 1g "${device_args[@]}" \
    -e GAMESCOPE_REFRESH=90 -v "$volume:/home/retro" -v "$root/tests:/tests:ro" \
    "$image" 'exec bash /tests/with-udmabuf.sh python3 /tests/native-headless.py'
for refresh in 60 90 120 144; do
    printf 'CPU virtual native acceptance at %s Hz (not Wolf GPU acceptance)\n' "$refresh"
    docker run --rm --network none --memory 3g --cpus 3 --shm-size 1g "${device_args[@]}" \
        -e GAMESCOPE_REFRESH="$refresh" \
        -v "$volume:/home/retro" -v "$root/tests:/tests:ro" \
        "$image" 'cp /tests/virtual-wrapper.sh /usr/local/bin/kwin_wayland_wrapper; chmod +x /usr/local/bin/kwin_wayland_wrapper; exec bash /tests/with-udmabuf.sh python3 /tests/native-headless.py'
done
for failure in compositor parent mode; do
    docker run --rm --network none --memory 3g --cpus 3 --shm-size 1g "${device_args[@]}" \
        -e FAILURE_TEST="$failure" -e GAMESCOPE_REFRESH=144 \
        -v "$volume:/home/retro" -v "$root/tests:/tests:ro" \
        "$image" 'cp /tests/virtual-wrapper.sh /usr/local/bin/kwin_wayland_wrapper; chmod +x /usr/local/bin/kwin_wayland_wrapper; exec bash /tests/with-udmabuf.sh python3 /tests/native-headless.py'
done
for exit_test in probe-stall logout; do
    docker run --rm --network none --memory 3g --cpus 3 --shm-size 1g "${device_args[@]}" \
        -e EXIT_TEST="$exit_test" -e GAMESCOPE_REFRESH=60 \
        -v "$volume:/home/retro" -v "$root/tests:/tests:ro" \
        "$image" 'cp /tests/virtual-wrapper.sh /usr/local/bin/kwin_wayland_wrapper; chmod +x /usr/local/bin/kwin_wayland_wrapper; exec bash /tests/with-udmabuf.sh python3 /tests/native-headless.py'
done
# Full application sandbox gate matches the existing production policy. Core
# KWin checks above deliberately retain default Docker caps/security instead.
bash "$root/tests/production-policy.sh" "$image" "$volume"
