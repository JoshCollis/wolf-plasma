# syntax=docker/dockerfile:1.7
ARG BASE_IMAGE=ghcr.io/games-on-whales/base-app:fedora
FROM ${BASE_IMAGE} AS themes
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN dnf install -y --setopt=install_weak_deps=False python3 tar gzip && dnf clean all
COPY build/install-themes.py /tmp/install-themes.py
RUN curl -fSL --retry 3 --max-time 180 \
      https://codeload.github.com/dracula/gtk/tar.gz/71640b9456110f3bac2130d0b387a3154a9fb4d2 -o /tmp/dracula.tar.gz && \
    echo '434013c854e82b509e633a03270b755f2d4b098c49d46680cafd4959502f3543  /tmp/dracula.tar.gz' | sha256sum -c - && \
    python3 /tmp/install-themes.py /tmp/dracula.tar.gz /assets

FROM ${BASE_IMAGE}
ARG BASE_IMAGE
ARG BASE_DIGEST=unrecorded-local-build
ARG IMAGE_SOURCE
ARG IMAGE_REVISION=local
LABEL org.opencontainers.image.title="wolf-plasma" \
      org.opencontainers.image.description="Plasma 6 X11 desktop for Games-on-Whales Wolf" \
      org.opencontainers.image.source=${IMAGE_SOURCE} \
      org.opencontainers.image.revision=${IMAGE_REVISION} \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.base.name=${BASE_IMAGE} \
      org.opencontainers.image.base.digest=${BASE_DIGEST}
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
# Use only this base's release repositories. Fail closed at its declared EOL.
RUN source /etc/os-release && test "$ID" = fedora && \
    test -n "$SUPPORT_END" && test "$(date -u +%F)" '<' "$SUPPORT_END" && \
    dnf upgrade -y --refresh --setopt=install_weak_deps=False && \
    dnf install -y --setopt=install_weak_deps=False \
      plasma-desktop plasma-workspace plasma-workspace-x11 kwin-x11 \
      plasma-discover plasma-discover-flatpak plasma-systemsettings plasma-pa \
      konsole dolphin kate ark kde-gtk-config \
      xdg-desktop-portal-kde xdg-desktop-portal-gtk \
      kvantum kvantum-qt5 papirus-icon-theme papirus-icon-theme-dark breeze-cursor-theme \
      flatpak bubblewrap dbus-daemon dbus-tools xdg-utils desktop-file-utils \
      shared-mime-info glibc-langpack-en at-spi2-core gtk3 gtk4 \
      libglvnd-glx libglvnd-egl vulkan-loader pulseaudio-utils \
      xdpyinfo xrandr xprop xorg-x11-xauth util-linux tini \
      ncdu iputils traceroute openssh-clients git curl wget jq ripgrep tmux nano less \
      rsync bind-utils iproute procps-ng lsof strace file diffutils patch \
      tar gzip bzip2 xz zstd unzip zip 7zip \
      python3 python3-pip nodejs npm gcc gcc-c++ make cmake pkgconf-pkg-config gdb && \
    dnf clean all && \
    chmod 0755 /usr/bin/bwrap && \
    mkdir -p /usr/share/wolf-plasma && \
    cp /etc/os-release /usr/share/wolf-plasma/base-os-release && \
    rpm -qa | sort > /usr/share/wolf-plasma/packages.txt
COPY --from=themes /assets/ /usr/share/
COPY overlay/ /
COPY LICENSE THIRD-PARTY.md /usr/share/doc/wolf-plasma/
RUN dnf install -y --setopt=install_weak_deps=False ostree bash-completion fastfetch fira-code-fonts gnupg2 pinentry-qt kwalletmanager5 kleopatra && dnf clean all && \
    ostree --repo=/var/lib/flatpak/repo init --mode=bare-user-only && \
    chmod 0755 /opt/gow/startup.sh /opt/wolf-plasma/*.sh /opt/wolf-plasma/*.py \
      /usr/local/bin/wolf-plasma-brave /etc/cont-init.d/05-plasma-runtime.sh \
      /etc/cont-init.d/40-plasma-dbus.sh /etc/cont-init.d/45-plasma-shell.sh && \
    chmod 0644 /opt/wolf-plasma/Dracula.colorscheme /opt/wolf-plasma/Dracula.profile && \
    desktop-file-validate /usr/share/applications/wolf-plasma-brave.desktop && \
    rm -rf /home/retro/.local && \
    rpm -qa | sort > /usr/share/wolf-plasma/packages.txt
ENV UNAME=desktop UMASK=022 TZ=UTC LANG=en_US.UTF-8
# Retain the official GoW /entrypoint.sh and its identity/device/NVIDIA hooks.
WORKDIR /home/retro
