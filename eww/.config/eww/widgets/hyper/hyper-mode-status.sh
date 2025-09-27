#!/usr/bin/env bash

mode=$(cat ~/.config/hypr/mode 2>/dev/null || echo "normal")

if [[ "$mode" == "hyper" ]]; then
  echo '{"text": "HYPER", "class": "hyper", "tooltip": "Hyper Mode - Press Super to exit"}'
else
  echo '{"text": "NORMAL", "class": "normal", "tooltip": "Normal Mode - Press Super to enter Hyper Mode"}'
fi 