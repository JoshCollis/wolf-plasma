#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mapfile -t scripts < <(printf '%s\n' "$root"/tests/*.sh "$root"/overlay/opt/wolf-plasma/*.sh \
    "$root"/overlay/opt/gow/startup.sh "$root"/overlay/etc/cont-init.d/*.sh \
    "$root"/overlay/usr/local/bin/wolf-plasma-brave)
for script in "${scripts[@]}"; do bash -n "$script"; done
docker run --rm -v "$root:/src:ro" koalaman/shellcheck:v0.10.0 \
    --severity=warning "${scripts[@]/$root/\/src}"
# Package versions intentionally follow the supported Fedora repositories.
docker run --rm -i hadolint/hadolint:v2.12.0 \
    hadolint --ignore DL3006 --ignore DL3007 --ignore DL3041 --ignore DL3059 --ignore SC1091 - < "$root/Dockerfile"
docker run --rm -v "$root:/src:ro" -w /src rhysd/actionlint:1.7.7 -shellcheck='' .github/workflows/image.yml
python3 - <<'PY'
import ast
from pathlib import Path
import json
import tomllib
for file in [Path('build/install-themes.py'), Path('overlay/opt/wolf-plasma/session.py'), *Path('tests').glob('*.py')]:
    ast.parse(file.read_text(), filename=str(file))
app = tomllib.loads(Path('examples/wolf-plasma.toml').read_text())['apps'][0]
runner = app['runner']
policy = json.loads(runner['base_create_json'])
assert runner['name'] == 'WolfPlasma'
assert policy['HostConfig']['Privileged'] is False
assert policy['HostConfig']['ShmSize'] >= 1024**3
assert '/sys/firmware' in policy['HostConfig']['MaskedPaths']
PY
