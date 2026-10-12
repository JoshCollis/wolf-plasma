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

## Distribution packages

KDE, GTK, Papirus, Kvantum, Flatpak and other Fedora packages retain their own
licences under `/usr/share/licenses` and `/usr/share/doc`. The package list is
`/usr/share/wolf-plasma/packages.txt`.

Wolf supplies NVIDIA userspace libraries at runtime. This image does not bundle
NVIDIA kernel drivers.
