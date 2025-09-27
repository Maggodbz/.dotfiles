#!/usr/bin/env bash

mode=$(cat ~/.config/hypr/mode 2>/dev/null || echo "normal")
new_mode=$([[ "$mode" == "normal" ]] && echo "hyper" || echo "normal")

[[ "$new_mode" == "hyper" ]] && hyprctl dispatch submap hyper || hyprctl dispatch submap reset
echo "$new_mode" > ~/.config/hypr/mode
