#!/usr/bin/env bash
# Keep an eww topbar alive on every monitor — at login, on monitor hotplug, and
# after suspend/hibernate (where external outputs re-appear and eww's layer
# surfaces get destroyed). This replaces the old one-shot autostart, so the bar
# comes up by itself and heals itself; you never run a script by hand.
#
# Strategy: reconcile once now, then keep reconciling. If socat is available we
# react instantly to Hyprland monitor events AND reconcile every few seconds as
# a backstop; otherwise we just poll. Reconcile is cheap and only rebuilds bars
# that are actually missing (see open-topbar-all.sh).
export PATH="$HOME/.local/bin:$PATH"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RECONCILE="$HERE/open-topbar-all.sh"
BACKSTOP=5 # seconds between safety reconciles

# Single instance, so repeated logins / config reloads don't stack daemons.
# Close fd 9 in children — otherwise eww inherits the lock and a restart of
# this daemon (without killing eww) silently no-ops.
LOCK="${XDG_RUNTIME_DIR:-/tmp}/desktop-shell-topbar.lock"
exec 9>"$LOCK"
flock -n 9 || exit 0

reconcile() { "$RECONCILE" 9>&-; }

reconcile

sig="$HYPRLAND_INSTANCE_SIGNATURE"
sock="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/hypr/$sig/.socket2.sock"

if command -v socat >/dev/null 2>&1 && [ -n "$sig" ]; then
    # Event-driven with a periodic backstop via read timeout.
    while :; do
        while :; do
            read -r -t "$BACKSTOP" line
            rc=$?
            if [ "$rc" -gt 128 ]; then
                reconcile # timed out — safety reconcile
                continue
            fi
            [ "$rc" -ne 0 ] && break # EOF: socket went away (Hyprland restart?)
            case "$line" in
                monitoradded*|monitorremoved*|monitoraddedv2*|focusedmon*) reconcile ;;
            esac
        done < <(socat -U - "UNIX-CONNECT:$sock" 9>&- 2>/dev/null)
        sleep 2 # wait for a fresh socket, then reconnect
    done
else
    # No socat: a plain safety poll covers login, hotplug and resume uniformly.
    while :; do
        sleep "$BACKSTOP"
        reconcile
    done
fi
