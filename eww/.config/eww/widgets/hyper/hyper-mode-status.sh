#!/bin/bash

# Read the current mode from the file
mode=$(cat ~/.config/hypr/mode 2>/dev/null || echo "normal")

# Return JSON with appropriate values
case "$mode" in
  "hyper")
    echo '{"text": "HYPER", "class": "hyper", "tooltip": "Hyper Mode"}'
    ;;
  *)
    echo '{"text": "NORMAL", "class": "normal", "tooltip": "Normal Mode"}'
    ;;
esac 