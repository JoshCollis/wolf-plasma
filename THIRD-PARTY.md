# Third-party components

## Games-on-Whales

Base image and startup hooks: [games-on-whales/gow](https://github.com/games-on-whales/gow),
MIT licence. The resolved base image name and digest are recorded in OCI labels
by the publishing workflow.

## Dracula

Themes by EliverLara and contributors: [dracula/gtk](https://github.com/dracula/gtk),
revision `71640b9456110f3bac2130d0b387a3154a9fb4d2`.

The image includes GTK assets, Plasma 6 themes, colour schemes, Dracula-purple
Kvantum and Dracula Aurorae decorations. Packaging removes online theme
installation dependencies and selects Papirus-Dark icons, purple colours and the
Breeze cursor.

The upstream licence is installed at `/usr/share/doc/wolf-plasma/dracula/LICENSE`.
Plasma theme metadata declares GPL-3.0+; Aurorae metadata declares GPLv3.
These assets are not covered by the project's MIT licence.

## ClusterCut

[keithvassallomt/ClusterCut](https://github.com/keithvassallomt/ClusterCut),
version `0.4.4`, GPLv3. The unmodified upstream x86_64 RPM and matching source
archive are pinned with SHA-256 checksums in the Dockerfile. Its licence and
source archive (including build scripts and dependency lockfiles) are included
at `/usr/share/doc/wolf-plasma/clustercut/`. Upstream source is also available at
<https://github.com/keithvassallomt/ClusterCut/tree/v0.4.4>.

## Xwayland

Upstream [Xwayland 24.1.14](https://xorg.freedesktop.org/archive/individual/xserver/xwayland-24.1.14.tar.xz),
SHA-256 `4eb6b98d678299a4b96138d886345b294130695760345ef84596225a8224078a`.
The private rootful binary has the project's small `build/xwayland-rootful-refresh.patch`.
Matching source, patch and upstream `COPYING` (MIT/X11 and other notices) are
included at `/usr/share/doc/wolf-plasma/xwayland/`. The system Fedora RPM is
retained; the desktop explicitly launches `/usr/local/libexec/wolf-plasma/Xwayland`.
The serial Present COPY diagnostic and its source are project MIT code.

## Distribution packages

KDE, GTK, Papirus, Kvantum, Flatpak and other Fedora packages retain their own
licences under `/usr/share/licenses` and `/usr/share/doc`. The package list is
`/usr/share/wolf-plasma/packages.txt`.

Wolf supplies NVIDIA userspace libraries at runtime. This image does not bundle
NVIDIA kernel drivers.
