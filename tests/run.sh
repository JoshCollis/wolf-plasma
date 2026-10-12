#!/usr/bin/env bash
set -euo pipefail
image=${1:-wolf-plasma:local}
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
docker run --rm --network none --entrypoint bash \
    -v "$root/tests:/tests:ro" "$image" /tests/image.sh
docker run --rm --network none --entrypoint python3 \
    -v "$root/tests:/tests:ro" "$image" /tests/runtime.py
docker run --rm --network none --entrypoint python3 -e TMPDIR=/home/retro \
    -v "$root/tests:/tests:ro" "$image" /tests/gpg-lifecycle.py
python3 "$root/tests/gpg-crash.py" "$image"
docker run --rm --network none -v "$root/tests:/tests:ro" "$image" 'bash /tests/shell.sh'
# Recreate with the same disposable home: verify state across container lifetime.
volume=$(docker volume create)
trap 'docker volume rm "$volume" >/dev/null' EXIT
for pass in 1 2; do
    printf 'Headless container creation %s\n' "$pass"
    docker run --rm --network none --security-opt seccomp=unconfined \
        --security-opt apparmor=unconfined --shm-size 1g \
        -v "$volume:/home/retro" -v "$root/tests:/tests:ro" \
        "$image" 'gosu "$UNAME" bash /tests/headless.sh'
done
docker run --rm --network none --security-opt seccomp=unconfined \
    --security-opt apparmor=unconfined --shm-size 1g -e FAILURE_TEST=xwayland \
    -v "$volume:/home/retro" -v "$root/tests:/tests:ro" \
    "$image" 'exec gosu "$UNAME" bash /tests/headless.sh'
