#!/usr/bin/env bash

volume=$(pactl get-sink-volume @DEFAULT_SINK@ | awk 'NR==1 {print $5}' | tr -d '%')
muted=$(pactl get-sink-mute @DEFAULT_SINK@ | grep -c "yes")

[[ "$muted" -eq 1 ]] && echo "audio-volume-muted" && exit
[[ "$volume" -le 33 ]] && echo "audio-volume-low" && exit
[[ "$volume" -le 66 ]] && echo "audio-volume-medium" && exit
echo "audio-volume-high"