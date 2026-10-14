#!/usr/bin/env bash
set -euo pipefail
image=${1:-wolf-plasma:local}
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
python3 "$root/tests/refresh.py"
docker run --rm --network none --entrypoint python3 \
    -v "$root/tests:/tests:ro" "$image" /tests/refresh.py
docker run --rm --network none --entrypoint bash \
    -v "$root/tests:/tests:ro" "$image" -ec 'chown -R 1000:1000 /home/retro; mkdir -p /run/user/1000; chown 1000:1000 /run/user/1000; chmod 0700 /run/user/1000; exec gosu 1000:1000 python3 /tests/refresh-headless.py'
docker run --rm --network none --entrypoint bash \
    -v "$root/tests:/tests:ro" "$image" /tests/image.sh
docker run --rm --network none --entrypoint python3 \
    -v "$root/tests:/tests:ro" "$image" /tests/runtime.py
docker run --rm --network none --entrypoint python3 -e TMPDIR=/home/retro \
    -v "$root/tests:/tests:ro" "$image" /tests/gpg-lifecycle.py
python3 "$root/tests/gpg-crash.py" "$image"
docker run --rm --network none -v "$root/tests:/tests:ro" "$image" \
    'gosu "$UNAME" python3 /tests/refresh-functional.py'
docker run --rm --network none -v "$root/tests:/tests:ro" "$image" 'bash /tests/shell.sh'
# Recreate with the same disposable home: verify state across container lifetime.
volume=$(docker volume create)
network=''
trap 'docker volume rm "$volume" >/dev/null; if [[ -n $network ]]; then docker network rm "$network" >/dev/null; fi' EXIT
# ClusterCut's mDNS registration needs a non-loopback interface. An internal
# disposable network supplies it without granting these desktop tests LAN/WAN access.
# Its local-IP detector also needs a default route; the internal bridge still
# blocks external traffic even with that route installed inside the container.
network=$(docker network create --internal "wolf-plasma-test-${volume:0:12}")
for pass in 1 2; do
    printf 'Headless container creation %s\n' "$pass"
    refresh=60
    if [[ $pass = 2 ]]; then refresh=90; fi
    docker run --rm --network "$network" --cap-add NET_ADMIN --security-opt seccomp=unconfined \
        -e GAMESCOPE_REFRESH="$refresh" \
        --security-opt apparmor=unconfined --shm-size 1g \
        -v "$volume:/home/retro" -v "$root/tests:/tests:ro" \
        "$image" 'ip route add default dev eth0 && gosu "$UNAME" bash /tests/headless.sh'
done
docker run --rm --network "$network" --cap-add NET_ADMIN --security-opt seccomp=unconfined \
    --security-opt apparmor=unconfined --shm-size 1g -e FAILURE_TEST=xwayland -e GAMESCOPE_REFRESH=144 \
    -v "$volume:/home/retro" -v "$root/tests:/tests:ro" \
    "$image" 'ip route add default dev eth0 && exec gosu "$UNAME" bash /tests/headless.sh'
