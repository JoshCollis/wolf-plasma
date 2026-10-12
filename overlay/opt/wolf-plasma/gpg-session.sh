#!/usr/bin/env bash
set -euo pipefail
# Keep keys/configuration in the user's home; never create or import a key here.
home=${GNUPGHOME:-$HOME/.gnupg}
if [[ ! -d $home ]]; then
    (umask 077; mkdir -p "$home")
fi
# Refresh the agent's saved display after container recreation or reconnection.
# The selected Pinentry and user gpg-agent.conf remain under GnuPG's control.
if ! timeout 10 gpg-connect-agent updatestartuptty /bye >/dev/null 2>&1; then
    printf '%s\n' 'GPG agent display setup failed; wallet/key tools can retry when opened.' >&2
fi
