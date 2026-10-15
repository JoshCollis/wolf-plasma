# wolf-plasma

Fedora-based KDE Plasma 6 desktop for [Wolf](https://github.com/games-on-whales/wolf).
Built on the official [Games-on-Whales base-app](https://github.com/games-on-whales/gow),
using Xwayland to display a Plasma X11 session inside Wolf. Supports `linux/amd64`.

## Included

- Dracula Plasma, GTK and Kvantum themes, Dracula window decorations and Papirus-Dark icons.
- Konsole with Fira Code, Bash completion, a coloured Git prompt and Fastfetch.
- Dolphin, Kate, Ark, Plasma Settings and audio controls.
- ClusterCut 0.4.4 (native X11), autostarting in the tray for clipboard sync.
- Discover with Flathub; Brave installs as a user Flatpak on first launch.
- Git, Python, Node.js/npm, GCC/G++, CMake, GDB, network diagnostics and archive tools.

GTK 4/libadwaita applications use dark mode but may not match the Dracula theme.
Flatpak appearance depends on the application's runtime.

## Build

```sh
bash tests/lint.sh
docker build --pull -t wolf-plasma:local .
bash tests/run.sh wolf-plasma:local
```

Docker and network access are required for the build. Tests use disposable
containers, a temporary volume and an internal-only test network. An optional
Brave sandbox test downloads the browser and its runtime:

```sh
python3 tests/sandbox-run.py wolf-plasma:local
```

The build uses Fedora packages from the base image's release and rejects a base
past its declared support date. Rootful Xwayland is built from checksum-pinned
24.1.14 source with a narrow negotiated-refresh patch; Fedora advancing past
that version intentionally fails the build pending revalidation. See
[high-refresh support and acceptance](docs/high-refresh.md).

The official GoW `:fedora` tag currently contains Fedora 44. An isolated build
and the full software/headless suite passed without package or session changes;
see the [Fedora 44 experiment](docs/fedora-44.md) for the tested digest, versions
and remaining hardware/frame-cadence checks. Existing containers remain unchanged
until explicitly recreated with a rebuilt image.

## Wolf configuration

Use [examples/wolf-plasma.toml](examples/wolf-plasma.toml) as the application
configuration. Set the image name and an independent persistent home directory.
For profile-based configurations, place the application under `profiles.apps`.

Wolf supplies the Wayland socket, audio, input devices and GPU libraries. The host
must provide `/dev/fuse` for Flatpak document portals.

The example grants capabilities and relaxes seccomp/AppArmor for nested Flatpak
sandboxes. It is intended for a trusted desktop, not isolation between untrusted
users. Do not expose the Docker socket to the desktop.

Runtime defaults:

- User: `desktop`, UID/GID `1000:1000`
- Home: `/home/retro` (the GoW/Wolf mount path)
- Time zone: `UTC`
- Umask: `022`

Override these with `UNAME`, `PUID`, `PGID`, `HOME`, `TZ` and `UMASK` as needed.
Keep the home mount and its ownership consistent with the configuration.

## User settings

The persistent home stores documents, application data and installed Flatpaks.
Theme and desktop defaults apply to fresh profiles. Later launches preserve user
settings; existing Bash configuration files are not replaced. Konsole's menu bar
is hidden by default; `Alt+M` restores it.

Brave setup runs in the background. If it fails, run `wolf-plasma-brave` to retry.
Its log is `~/.local/state/wolf-plasma/brave-bootstrap.log`. Manage application
updates through Discover or `flatpak update --user`.

## Clipboard sync

[ClusterCut](https://github.com/keithvassallomt/ClusterCut) starts minimized with
each Plasma session, including existing profiles. Its upstream defaults enable
automatic sending and receiving with paired devices. Open ClusterCut from the
tray or application launcher and pair your client once; the image does not ship
shared identities, PINs or trusted peers. Install ClusterCut on the client too:
this is independent of Moonlight's clipboard support.
Both launchers set `WEBKIT_DISABLE_DMABUF_RENDERER=1` to avoid a blank WebKit UI
in the container's X11 session.

Settings and pairing keys remain in the persistent home under
`~/.config/app.clustercut.clustercut` (or the corresponding XDG path).
Clipboard history uses memory and the application's cache directory; it should
not be treated as durable storage. Existing preferences are not overwritten.
Disable autostart in Plasma Settings → Autostart if you do not want clipboard
sharing. Automatic sync can be switched off in ClusterCut; clipboard history and
file transfers are also enabled by upstream defaults, so avoid pairing devices
you do not trust.

**Networking needs deployment configuration.** The image does not change Wolf's
network mode or publish ports. ClusterCut uses UDP 4654 for sync, TCP 4654 for
pairing and UDP 5353 multicast for mDNS discovery. A Docker bridge generally
does not carry LAN discovery: publish TCP and UDP 4654 on the Wolf host, allow
them only on your trusted LAN/VPN, and manually add the host's reachable address
from the client. See the commented port example in
[examples/wolf-plasma.toml](examples/wolf-plasma.toml). Multiple desktops need
distinct host ports. LAN-attached networking can provide discovery instead,
but requires a deliberate deployment choice; do not expose these ports publicly.
Do not use Docker's `--network none` for ClusterCut: this release's local-IP
detector requires a non-loopback interface and a default route.

## GPG-backed wallets

Kleopatra, KWallet Manager and Qt Pinentry are included. Fedora's Pinentry wrapper
selects the graphical Qt dialog in the Plasma session. Session startup refreshes
the GPG agent's saved display and Xauthority environment without replacing user
GPG configuration.

Create or import a personal, encryption-capable key in Kleopatra, then select it
when creating a GPG-encrypted wallet in KWallet Manager. A signing-only key is not
sufficient. Keys remain in `~/.gnupg` (or your custom `GNUPGHOME`), and wallet files
remain in the persistent home. No keys or passphrases are supplied by the image.
Unlocking uses a graphical passphrase prompt; automatic PAM login unlocking is
not configured for Wolf sessions.

### Container recreation and keyboxd locks

The session supervisor leases the default `~/.gnupg` for the entire desktop
lifetime (persistent `.wolf-plasma-lifecycle.lock`, never unlinked). It acquires
that lease before starting desktop clients and, after stopping them, asks
`gpgconf --homedir <default-home> --kill all` to cleanly stop this home's daemons.
A second cooperating session or an already-running local GPG daemon prevents
startup instead of taking over a live keyboxd lock. Shutdown is bounded; a crash
or forced container stop still requires the next-start checks.

**Cross-container automatic recovery is opt-in.** Set
`WOLF_PLASMA_GPG_ISOLATED_HOME=1` in the Wolf application environment only after
confirming all these deployment conditions:

- The default home is on a local filesystem, dedicated to one Wolf profile.
- No other running container (including an older image), host process, remote
  client, backup restore, or independent GPG service accesses that home.
- Only one desktop/container uses the home at a time; the old container has
  fully stopped before its replacement starts. Do not enable it for NFS/CIFS or
  another shared/distributed filesystem, or when mounting a host's personal home.

This is an **operator isolation assertion**, not something the container can
prove. Advisory `flock` excludes only cooperating processes that use the same
lease inode. It does not prove a foreign Docker hostname is dead, nor exclude
older images or remote clients. Without the assertion a stale/foreign keyboxd
lock fails startup with an explanation; no lock is removed. Do not enable the
flag merely to silence that error on an unknown/shared deployment.

Recovery removes only `public-keys.d/pubring.db.lock`, after checking the lease,
local daemons and same-host PID, owner/permissions, regular-file type, strict GPG
owner record, unchanged contents/inode and directory identities. Symlink paths,
malformed records, unexpected hardlinks, symlinked databases and unsafe permissions
fail closed.
GnuPG's normal two-link dotlock is accepted only with its matching `.#lk...`
companion in the same directory; the companion is left untouched. The default
`.gnupg` must be UID-owned and mode `0700`; unsafe homes are not chmodded or
repaired automatically. Locks, configs and databases are not broadly cleaned.
`pubring.db`, private keys and wallet files are never deleted or rewritten by
recovery, and keyboxd/locking remain enabled.

Any nonempty custom `GNUPGHOME` remains entirely user-managed: no lifecycle
lease, automatic lock removal or shutdown is performed for it. Agent display
refresh still respects that setting and `gpg-agent.conf`. Even a custom path
aliasing the default disables management. A same-UID GPG daemon in any other
home also conservatively blocks default-home takeover at startup. Shared-home
and independent-service lifecycles need external coordination/manual diagnosis;
this image is not a general-purpose GnuPG lock repair utility.

The test suite uses only disposable keys/homes: actual `use-keyboxd`, real
signing plus encryption subkeys, two forced-stop/SIGKILL recreations across
three hostnames, unchanged private-key/config hashes, encrypt/decrypt, live lock
and competing lease preservation, malformed/symlink refusal and clean shutdown.
For the original failure reproduction against an older local image:

```sh
python3 tests/gpg-crash.py wolf-plasma:gpg-test --baseline # expected timeout/failure
python3 tests/gpg-crash.py wolf-plasma:local             # expected pass
```

## Publishing

GitHub Actions builds and tests pull requests. Successful builds on `main`
publish `ghcr.io/<owner>/wolf-plasma:latest` and a commit-specific tag. Manual runs
and the weekly scheduled build on `main` also publish. Publication does not deploy
the image to Wolf.

After the first publication, set the GHCR package visibility to **Public** in its
package settings. A public repository does not make its container package public.

## Licence

Project code is MIT-licensed. Bundled themes and distribution packages retain
their own licences; see [THIRD-PARTY.md](THIRD-PARTY.md).
