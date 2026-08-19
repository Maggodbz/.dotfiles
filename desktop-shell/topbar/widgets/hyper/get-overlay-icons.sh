#!/usr/bin/env bash
# Returns a JSON array of icon paths for overlay apps parked in workspace 42.
# Icon locations and the class -> icon map come from the active theme.

source "$(dirname "${BASH_SOURCE[0]}")/../../theme/current/icons.sh"

OVERLAY_WS=42

icons=()
while read -r cls; do
    icon=$(app_icon_path "$cls") && icons+=("\"$icon\"")
done < <(hyprctl clients -j 2>/dev/null | jq -r ".[] | select(.workspace.id == $OVERLAY_WS) | .class")

printf '[%s]' "$(IFS=,; echo "${icons[*]}")"
