# Fedora 44 experiment

The official `ghcr.io/games-on-whales/base-app:fedora` tag now resolves to
Fedora 44. The Dockerfile and GitHub workflow already follow this mutable tag;
no Fedora repository replacement or in-container release upgrade is needed.
Existing images/containers do not change merely because the upstream tag moves.

## Candidate

* Index digest: `sha256:7771447033d84609ec769505d2df10fc14b80ddac69763f792d8c9bb394e491f`
* amd64 manifest: `sha256:18279fde493373bda407cb116f9b154db9b9b9682c46e94128c0383af62bff0b`
* `/etc/os-release`: Fedora 44, declared support end `2027-05-19`.
* Base Xwayland: `24.1.14-1.fc44`; the private patched 24.1.14 build remains
  subject to the existing version/security guard.
* Official entrypoint, identity/device/NVIDIA hooks and NVIDIA library paths
  remain present. Plasma X11 is still an optional community-supported session.

## Reproduce without publishing or deployment

```sh
base=ghcr.io/games-on-whales/base-app@sha256:7771447033d84609ec769505d2df10fc14b80ddac69763f792d8c9bb394e491f
docker build --pull --build-arg BASE_IMAGE="$base" \
  --build-arg BASE_DIGEST="${base#*@}" -t wolf-plasma:fedora44-experiment .
bash tests/run.sh wolf-plasma:fedora44-experiment
python3 tests/sandbox-run.py wolf-plasma:fedora44-experiment
```

These tests use disposable homes, keys, networks and containers. Never point them
at a real desktop home. Keep the experiment tag separate from deployed images.
The sandbox test downloads a fresh user Brave installation and requires the
example's host namespace policy. Neither test proves Wolf/NVIDIA streaming,
Moonlight input/audio or client-side frame cadence.

## Results — 2026-10-15

Built unchanged source at `834ae01` successfully with this base. Candidate image:
`wolf-plasma:fedora44-experiment`, config ID
`sha256:742820b262d955801aa20b8c42418842a36be88f588cf4cfed1a44135256fe3e`.
The temporary image tag was removed after validation; it was not pushed to a
registry. Use the reproduction commands above to rebuild the same candidate.

Versions: Plasma/KWin/Discover 6.7.5, Flatpak 1.18.4, Bubblewrap 0.12.0,
GnuPG 2.4.9, Python 3.14.8 and Node 22.23.1/npm 10.9.8. The distro Node
implementation is packaged as `nodejs22-bin`; the `node` and `npm` commands work.
No package renaming, repository mixing, or application changes were required.

Passed:

* Local lint and refresh-contract unit tests.
* Full image build, patched Xwayland compilation and upstream tests
  (3 passed, 2 skipped, 0 failed).
* Entire `tests/run.sh` suite on the test host, including image assets/commands,
  runtime socket isolation, shell defaults, GPG lock safety and real keyboxd
  SIGKILL/recreation/encrypt/decrypt tests using disposable keys.
* Software-only parent/X11 mode matrix at 60/90/120/144 Hz for both
  1920×1200 and 1912×1192, including mismatched-parent rejection.
* Real headless Plasma/KWin sessions at 1280×720, including 60/90 Hz home
  recreation and the 144 Hz Xwayland-failure/cleanup case. ClusterCut autostart,
  clipboard listener, pairing identity persistence and graphical GPG Pinentry
  open/cancel checks passed.
* Optional `tests/sandbox-run.py` with the example's exact `base_create_json`
  policy: fresh user Flathub/Brave 1.97.57 installation, unprivileged and nested
  PID/mount namespaces, non-setuid Bubblewrap, and sandboxed Brave headless DOM
  marker all passed, without `--no-sandbox`. The host's Python 3.9 ran this
  host-side harness using a temporary venv with Tomli 2.2.1 as the `tomllib`
  compatibility shim; the image itself uses Python 3.14.

The display-free Brave test logged portal/display warnings and a missing
`/dev/fuse` document mount, plus a p11-kit startup warning. It nevertheless
returned the expected DOM. This does **not** establish functional GUI portals,
file pickers, host certificate integration, or GPU acceleration. The deployment
must still provide `/dev/fuse` as documented in the Wolf example.

The functional test's software cadence samples passed its tolerance at
60/90/120 Hz, but **not at 144 Hz** (approximately 165 callbacks/s). The existing
suite reports this measurement separately and still passes its negotiation
contract. Do not interpret the passing mode matrix or suite exit status as
certification of 144 FPS frame pacing, or attribute that variance to the release
upgrade without a matched Fedora 43 comparison.

The initial local build was deliberately stopped when the root filesystem had
only about 1.6 GiB free; no unrelated cache/image pruning was performed. Building
and testing continued on a host with sufficient Docker storage, using a separate
image tag, disposable homes/keys and test network. Raw build/test logs are kept
under the ignored local `artifacts/fedora-44/` directory.

Live Wolf/Moonlight GPU rendering, input, audio and real client frame cadence
have not been tested. Existing desktop configuration, homes and containers have
not been changed. No image has been pushed or deployed by this experiment.
