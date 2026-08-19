#!/usr/bin/env bash
# Ensure an eww topbar exists on every enabled monitor.
#
# Idempotent and self-healing: safe to run repeatedly (login, monitor hotplug,
# after suspend/hibernate). It checks the actual layer surface per monitor
# rather than trusting eww's window list, so a bar that silently vanished on
# resume gets rebuilt.
#
# Hyprland's exec-once inherits a minimal PATH without ~/.local/bin where eww
# lives, so fix that up first. Without it the whole script silently does
# nothing at login while working perfectly from a terminal.
export PATH="$HOME/.local/bin:$PATH"

LOG="${XDG_CACHE_HOME:-$HOME/.cache}/eww/open-topbar.log"
mkdir -p "$(dirname "$LOG")"
# Keep the log from growing without bound across many reconciles.
if [ -f "$LOG" ] && [ "$(wc -c <"$LOG" 2>/dev/null || echo 0)" -gt 1000000 ]; then
    : >"$LOG"
fi
log() { printf '%s %s\n' "$(date -Is)" "$*" >>"$LOG"; }

# Only an explicit `true` counts as off: `hyprctl monitors` lists active outputs
# anyway, and matching on == false turns any schema change into "zero monitors",
# which silently leaves the screen with no bar at all.
enabled_monitors() {
    hyprctl monitors -j 2>/dev/null \
        | jq -r '.[] | select(.disabled != true) | .name' 2>/dev/null
}

# Whatever the reason hyprctl gave us nothing - not on PATH, IPC unreachable,
# output we cannot parse - a bar on the focused output beats no bar. It loses
# only the per-monitor workspace highlight, which needs a name to compare.
open_fallback_bar() {
    ensure_daemon || { log "eww daemon unreachable"; return 1; }
    if eww active-windows 2>/dev/null | cut -d: -f1 | grep -qx topbar-fallback; then
        return 0
    fi
    log "opening unscoped fallback bar"
    eww open topbar --id topbar-fallback --arg "monitor=" || log "!! fallback bar failed"
}

monitor_has_bar() { # $1 = monitor name
    hyprctl layers -j 2>/dev/null | jq -e --arg m "$1" \
        '.[$m].levels | to_entries[].value[]? | select(.namespace == "eww-topbar")' \
        >/dev/null 2>&1
}

ensure_daemon() {
    eww active-windows >/dev/null 2>&1 && return 0
    eww daemon >/dev/null 2>&1 || return 1
    for _ in $(seq 1 25); do
        eww active-windows >/dev/null 2>&1 && return 0
        sleep 0.2
    done
    return 1
}

# At login this can fire before Hyprland has enumerated its outputs, so wait
# for at least one to appear rather than assuming they are already there.
mapfile -t MONITORS < <(enabled_monitors)
for _ in $(seq 1 50); do
    ((${#MONITORS[@]})) && break
    sleep 0.2
    mapfile -t MONITORS < <(enabled_monitors)
done
if ((${#MONITORS[@]} == 0)); then
    # Log what hyprctl actually said; discarding it is why this looked like
    # "no monitors found" rather than a named failure.
    log "no monitors from hyprctl: $(hyprctl monitors -j 2>&1 | head -c 300)"
    open_fallback_bar
    exit 0
fi

ensure_daemon || { log "eww daemon unreachable"; exit 1; }

# Bars are keyed by monitor NAME (topbar-<name>), and eww's --screen accepts a
# name, so a bar stays tied to the right output no matter what order Hyprland
# enumerates them in.
declare -A want=()
for m in "${MONITORS[@]}"; do want["topbar-$m"]="$m"; done

# Snapshot the ids eww currently believes are open, so we only ever close what
# actually exists (no "no such window" noise).
declare -A open_ids=()
while read -r id; do
    [ -n "$id" ] && open_ids["$id"]=1
done < <(eww active-windows 2>/dev/null | cut -d: -f1)

# Close bars for monitors that are gone, plus any leftover index-based ids.
for id in "${!open_ids[@]}"; do
    [[ "$id" == topbar-* ]] || continue
    [[ -v want["$id"] ]] && continue
    log "close stale $id"
    eww close "$id" >/dev/null 2>&1
done

changed=0
for m in "${MONITORS[@]}"; do
    id="topbar-$m"
    monitor_has_bar "$m" && continue
    # No live layer on this output. If eww still thinks a window with this id is
    # open, it is a half-dead surface (typical after resume) — close it first.
    if [[ -v open_ids["$id"] ]]; then
        eww close "$id" >/dev/null 2>&1
        sleep 0.1
    fi
    log "open $id on $m"
    eww open topbar --screen "$m" --id "$id" --arg "monitor=$m" \
        || log "!! failed to open $id"
    changed=1
done

[ "$changed" = 1 ] && log "reconciled: ${MONITORS[*]}"
exit 0
