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
# Native X11 build: the upstream Flatpak does not support clipboard sync on X11.
# Keep the matching source and licence alongside the unmodified GPLv3 binary.
RUN curl -fSL --retry 3 --max-time 180 \
      https://github.com/keithvassallomt/ClusterCut/releases/download/v0.4.4/ClusterCut-0.4.4-1.x86_64.rpm -o /tmp/clustercut.rpm && \
    echo '30779025277a9de199eb5328e978164d5da8151729d1d5adeca5d1c301f59872  /tmp/clustercut.rpm' | sha256sum -c - && \
    mkdir -p /assets/doc/wolf-plasma/clustercut && \
    curl -fSL --retry 3 --max-time 180 \
      https://codeload.github.com/keithvassallomt/ClusterCut/tar.gz/refs/tags/v0.4.4 \
      -o /assets/doc/wolf-plasma/clustercut/source-v0.4.4.tar.gz && \
    echo '7fa0a6bc869c2cc6ce9e6b5d720457df3f4fe20d1c909b1b0bdcbc1ec3878e31  /assets/doc/wolf-plasma/clustercut/source-v0.4.4.tar.gz' | sha256sum -c - && \
    tar -xOf /assets/doc/wolf-plasma/clustercut/source-v0.4.4.tar.gz ClusterCut-0.4.4/LICENSE \
      > /assets/doc/wolf-plasma/clustercut/LICENSE

FROM ${BASE_IMAGE} AS xwayland
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
# Pinned security release; refuse silently serving an older private binary after
# Fedora advances. See docs/high-refresh.md for the update/revalidation procedure.
RUN dnf install -y --setopt=install_weak_deps=False \
      gcc meson ninja-build patch tar xz python3 pkgconf-pkg-config \
      wayland-devel wayland-protocols-devel libepoxy-devel libdrm-devel \
      openssl-devel libtirpc-devel pixman-devel libX11-devel libXau-devel \
      libXdmcp-devel libXext-devel libXfixes-devel libXfont2-devel libXi-devel \
      libXinerama-devel libxkbfile-devel libXmu-devel libXrender-devel libXres-devel \
      libxshmfence-devel xorg-x11-proto-devel xorg-x11-xtrans-devel libXtst-devel \
      libXv-devel libxcvt-devel libdecor-devel liboeffis-devel libei-devel \
      mesa-libGL-devel mesa-libEGL-devel mesa-libgbm-devel audit-libs-devel \
      libselinux-devel libunwind-devel xcb-util-devel xcb-util-image-devel \
      xcb-util-wm-devel xcb-util-keysyms-devel xcb-util-renderutil-devel && dnf clean all
WORKDIR /build
# TLS/connection resets are not retried by curl's default --retry policy.
RUN curl -fSL --retry 3 --retry-all-errors --connect-timeout 30 --max-time 180 \
      https://xorg.freedesktop.org/archive/individual/xserver/xwayland-24.1.14.tar.xz -o source.tar.xz && \
    echo '4eb6b98d678299a4b96138d886345b294130695760345ef84596225a8224078a  source.tar.xz' | sha256sum -c - && \
    tar -xf source.tar.xz
COPY build/xwayland-rootful-refresh.patch /build/refresh.patch
COPY tests/xwayland-modes.py /build/test-modes.py
RUN patch --fuzz=0 -p1 -d xwayland-24.1.14 < refresh.patch && \
    python3 test-modes.py xwayland-24.1.14/hw/xwayland/xwayland-output.c && \
    meson setup out xwayland-24.1.14 --prefix=/usr --buildtype=release \
      -Ddefault_font_path=catalogue:/etc/X11/fontpath.d,built-ins \
      -Dxkb_dir=/usr/share/X11/xkb -Dxkb_bin_dir=/usr/bin -Dxkb_output_dir=/var/lib/xkb \
      -Dserverconfigdir=/usr/share/xwayland -Dxcsecurity=true -Dglamor=true -Ddri3=true && \
    meson compile -C out -j 2 && meson test -C out --print-errorlogs && \
    mkdir -p /assets/libexec/wolf-plasma /assets/doc/wolf-plasma/xwayland && \
    install -m 0755 out/hw/xwayland/Xwayland /assets/libexec/wolf-plasma/Xwayland && \
    cp source.tar.xz refresh.patch xwayland-24.1.14/COPYING /assets/doc/wolf-plasma/xwayland/ && \
    cp out/meson-logs/testlog.txt /assets/doc/wolf-plasma/xwayland/upstream-tests.txt

COPY build/present-probe.c /build/present-probe.c
# pkg-config intentionally emits separate compiler arguments.
# hadolint ignore=SC2046
RUN gcc -O2 -Wall -Werror present-probe.c -o /assets/libexec/wolf-plasma/present-probe \
      $(pkg-config --cflags --libs xcb xcb-present) && \
    cp present-probe.c /assets/doc/wolf-plasma/xwayland/

FROM ${BASE_IMAGE} AS runtime
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
    test "$(rpm --eval "%{lua: print(rpm.vercmp(\"$(rpm -q --qf '%{VERSION}' xorg-x11-server-Xwayland)\", \"24.1.14\"))}")" -le 0 && \
    chmod 0755 /usr/bin/bwrap && \
    mkdir -p /usr/share/wolf-plasma && \
    cp /etc/os-release /usr/share/wolf-plasma/base-os-release && \
    rpm -qa | sort > /usr/share/wolf-plasma/packages.txt
COPY --from=themes /assets/ /usr/share/
COPY --from=xwayland /assets/libexec/ /usr/local/libexec/
COPY --from=xwayland /assets/doc/ /usr/share/doc/
RUN /usr/local/libexec/wolf-plasma/Xwayland -version
COPY overlay/ /
COPY LICENSE THIRD-PARTY.md /usr/share/doc/wolf-plasma/
RUN --mount=from=themes,source=/tmp/clustercut.rpm,target=/tmp/clustercut.rpm \
    dnf install -y --setopt=install_weak_deps=False ostree bash-completion fastfetch fira-code-fonts gnupg2 pinentry-qt kwalletmanager5 kleopatra /tmp/clustercut.rpm && dnf clean all && \
    sed -i 's|^Exec=clustercut$|Exec=env GDK_BACKEND=x11 WEBKIT_DISABLE_DMABUF_RENDERER=1 /usr/bin/clustercut|' /usr/share/applications/ClusterCut.desktop && \
    ostree --repo=/var/lib/flatpak/repo init --mode=bare-user-only && \
    chmod 0755 /opt/gow/startup.sh /opt/wolf-plasma/*.sh /opt/wolf-plasma/*.py \
      /usr/local/bin/wolf-plasma-brave /etc/cont-init.d/05-plasma-runtime.sh \
      /etc/cont-init.d/40-plasma-dbus.sh /etc/cont-init.d/45-plasma-shell.sh && \
    chmod 0644 /opt/wolf-plasma/Dracula.colorscheme /opt/wolf-plasma/Dracula.profile && \
    desktop-file-validate /usr/share/applications/wolf-plasma-brave.desktop && \
    desktop-file-validate /etc/xdg/autostart/ClusterCut.desktop && \
    desktop-file-validate /usr/share/applications/ClusterCut.desktop && \
    rm -rf /home/retro/.local && \
    rpm -qa | sort > /usr/share/wolf-plasma/packages.txt
ENV UNAME=desktop UMASK=022 TZ=UTC LANG=en_US.UTF-8
# Retain the official GoW /entrypoint.sh and its identity/device/NVIDIA hooks.
WORKDIR /home/retro
