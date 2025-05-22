#!/bin/bash

# Create mode file if it doesn't exist
if [ ! -f ~/.config/hypr/mode ]; then
  echo "normal" > ~/.config/hypr/mode
fi

# Check current mode
MODE=$(cat ~/.config/hypr/mode)

if [[ "$MODE" == "hyper" ]]; then
  # Hyper mode active
  echo '{"text": "󰘳 HYPER", "class": "hyper", "tooltip": "Hyper Mode Active"}'
else
  # Normal mode
  echo '{"text": "NORMAL", "class": "normal", "tooltip": "Normal Mode"}'
fi 