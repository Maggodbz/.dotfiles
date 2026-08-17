#!/usr/bin/env bash
# Open the eww topbar on every active (non-disabled) monitor.
# eww --screen uses 0-based sequential indices, not hyprctl monitor IDs.

mapfile -t MONITORS < <(
    hyprctl monitors -j |
    jq -r '.[] | select(.disabled == false) | .name'
)

for i in "${!MONITORS[@]}"; do
    eww open topbar \
        --screen "$i" \
        --id "topbar-$i" \
        --arg "monitor=${MONITORS[$i]}"
done

