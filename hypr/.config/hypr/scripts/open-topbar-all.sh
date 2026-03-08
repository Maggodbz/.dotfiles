#!/usr/bin/env bash
# Open the eww topbar on every active (non-disabled) monitor.
# eww --screen uses 0-based sequential indices, not hyprctl monitor IDs.

COUNT=$(hyprctl monitors -j | jq '[.[] | select(.disabled == false)] | length')

for (( i=0; i<COUNT; i++ )); do
    eww open topbar --screen "$i" --id "topbar-$i"
done

