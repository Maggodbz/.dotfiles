#!/usr/bin/env bash

MODE_FILE="${XDG_RUNTIME_DIR:-/tmp}/desktop-shell/mode"
mkdir -p "$(dirname "$MODE_FILE")"

mode=$(cat "$MODE_FILE" 2>/dev/null || echo "normal")
new_mode=$([[ "$mode" == "normal" ]] && echo "hyper" || echo "normal")

[[ "$new_mode" == "hyper" ]] && hyprctl dispatch submap hyper || hyprctl dispatch submap reset
echo "$new_mode" > "$MODE_FILE"
