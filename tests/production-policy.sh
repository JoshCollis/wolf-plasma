#!/usr/bin/env bash
# Sourced only by host-side disposable application-test drivers.
# These are the parent-verified ALREADY-EXISTING Wolf application flags, not
# additions to any production profile. Application sandboxes remain enabled.
# shellcheck disable=SC2034 # Consumed by the sourcing host-side test driver.
production_policy=(--cap-add SYS_ADMIN --cap-add SYS_NICE --cap-add SYS_PTRACE
    --cap-add NET_RAW --cap-add MKNOD --cap-add NET_ADMIN
    --security-opt seccomp=unconfined --security-opt apparmor=unconfined
    --security-opt label=disable)
