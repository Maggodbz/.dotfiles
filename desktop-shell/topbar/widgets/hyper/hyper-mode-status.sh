#!/usr/bin/env bash

MODE_FILE="${XDG_RUNTIME_DIR:-/tmp}/desktop-shell/mode"
mode=$(cat "$MODE_FILE" 2>/dev/null || echo "normal")

if [[ "$mode" == "hyper" ]]; then
  echo '{"text": "HYPER", "class": "hyper", "tooltip": "Hyper Mode - Press Super to exit"}'
else
  echo '{"text": "NORMAL", "class": "normal", "tooltip": "Normal Mode - Press Super to enter Hyper Mode"}'
fi
