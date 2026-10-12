#!/usr/bin/env bash
# Run inside the disposable test image after GoW has created its desktop user.
set -euo pipefail
test "$UNAME" = desktop
test "$(id -u "$UNAME")" = 1000
test "$(getent passwd "$UNAME" | cut -d: -f6)" = /home/retro
command -v fastfetch
fc-match 'Fira Code' | grep -q 'FiraCode'
gosu "$UNAME" env TERM=xterm-256color bash -ic 'set -e; alias ll; alias neofetch; shopt -q histappend; test "$HISTCONTROL" = ignoreboth; test "$HISTSIZE" = 10000; test "$WOLF_PLASMA_SHELL_LOADED" = 1; declare -F _comp_load; [[ $PS1 == *"__wolf_git_prompt"* ]]; dir=$(mktemp -d); git init -qb sample "$dir"; cd "$dir"; test "$(__wolf_git_prompt)" = " (sample)"; fastfetch --pipe' 2>/tmp/shell-test.log || { cat /tmp/shell-test.log; exit 1; }
# Repeated startup must preserve custom dotfiles, prompts and dangling symlinks.
gosu "$UNAME" bash -c 'printf "\nPS1=custom-prompt\n" >> "$HOME/.bashrc"; rm "$HOME/.bash_profile"; ln -s missing-user-profile "$HOME/.bash_profile"'
before=$(sha256sum "$HOME/.bashrc")
/etc/cont-init.d/45-plasma-shell.sh
test "$before" = "$(sha256sum "$HOME/.bashrc")"
test -L "$HOME/.bash_profile"
gosu "$UNAME" env TERM=xterm-256color bash -ic 'test "$PS1" = custom-prompt' 2>/dev/null
# No banners or prompt work in scripts/noninteractive shells.
test -z "$(gosu "$UNAME" bash -c 'source /etc/profile.d/wolf-plasma-shell.sh')"
printf '%s\n' 'Neutral desktop identity, shell defaults, font and Fastfetch passed'
