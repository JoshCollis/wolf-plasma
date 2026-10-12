#!/usr/bin/env bash
set -euo pipefail
# useradd cannot seed an already-mounted home. Fill only absent Bash files,
# as the desktop user, and preserve both custom dotfiles and symlinks.
[[ $UNAME != root ]] || exit 0
gosu "$UNAME" bash -eu -c '
for file in .bashrc .bash_profile; do
    if [[ ! -e $HOME/$file && ! -L $HOME/$file ]]; then
        cp --no-clobber "/etc/skel/$file" "$HOME/$file"
    fi
done
'
