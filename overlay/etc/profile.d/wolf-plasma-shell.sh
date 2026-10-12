#!/usr/bin/env bash
# Bash defaults for the cloud desktop. User ~/.bashrc overrides remain last.
# Deliberately silent for scripts, remote commands and noninteractive shells.
[[ -n ${BASH_VERSION:-} && $- == *i* ]] || return 0
[[ ${WOLF_PLASMA_SHELL_LOADED:-} != 1 ]] || return 0
WOLF_PLASMA_SHELL_LOADED=1

HISTCONTROL=ignoreboth
HISTSIZE=10000
HISTFILESIZE=20000
shopt -s histappend checkwinsize
__wolf_history_sync() { history -a; history -n; }
PROMPT_COMMAND+=(__wolf_history_sync)

alias ls='ls --color=auto'
alias ll='ls -lah --color=auto'
alias la='ls -A --color=auto'
alias grep='grep --color=auto'
alias fastfetch='/usr/bin/fastfetch --config /usr/share/wolf-plasma/fastfetch.json'
alias neofetch='/usr/bin/fastfetch --config /usr/share/wolf-plasma/fastfetch.json'
alias neowofetch='/usr/bin/fastfetch --config /usr/share/wolf-plasma/fastfetch.json'

__wolf_git_prompt() {
    local branch
    branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null) || return 0
    printf ' (%s)' "$branch"
}
if [[ ${TERM:-dumb} != dumb ]]; then
    PS1='\[\e[38;2;189;147;249m\]\u\[\e[0m\] \[\e[38;2;139;233;253m\]\w\[\e[38;2;255;184;108m\]$(__wolf_git_prompt)\[\e[0m\]\n\$ '
fi
