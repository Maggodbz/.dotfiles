#!/usr/bin/env bash
# Reports the volume state; the active theme turns it into an icon path.

source "$(dirname "${BASH_SOURCE[0]}")/../../theme/current/icons.sh"

volume=$(pactl get-sink-volume @DEFAULT_SINK@ | awk 'NR==1 {print $5}' | tr -d '%')
muted=$(pactl get-sink-mute @DEFAULT_SINK@ | grep -c "yes")

if   [[ "$muted" -eq 1 ]];  then state=muted
elif [[ "$volume" -le 33 ]]; then state=low
elif [[ "$volume" -le 66 ]]; then state=medium
else                              state=high
fi

volume_icon_path "$state"
