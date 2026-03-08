#!/usr/bin/env bash
# Open the eww topbar on every active (non-disabled) monitor.

MONITORS=$(hyprctl monitors -j | jq -r '.[].id')

for id in $MONITORS; do
    eww open topbar --screen "$id" --id "topbar-$id"
done

