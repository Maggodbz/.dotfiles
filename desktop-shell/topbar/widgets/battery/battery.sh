#!/usr/bin/env bash
# Report battery state as JSON for the eww widget.
#
# Emits a *level* name ("charging", "critical", "low", "normal") rather than a
# colour, and asks the theme for the icon rather than naming a file: both belong
# to the theme, not to this script.

source "$(dirname "${BASH_SOURCE[0]}")/../../theme/current/icons.sh"

no_battery=$(printf '{"icon":"%s","percentage":"N/A","status":"Unknown","level":"normal","charging":false,"tooltip":"No battery found"}' \
    "$(battery_icon_path 60 false)")

# BAT0 wins when a machine exposes both.
battery_path=""
for candidate in /sys/class/power_supply/BAT1 /sys/class/power_supply/BAT0; do
    [[ -e "$candidate" ]] && battery_path="$candidate"
done

if [[ -z "$battery_path" ]]; then
    echo "$no_battery"
    exit 0
fi

percentage=$(cat "$battery_path/capacity" 2>/dev/null || true)
status=$(cat "$battery_path/status" 2>/dev/null || echo "Unknown")

if [[ ! "$percentage" =~ ^[0-9]+$ ]]; then
    echo "$no_battery"
    exit 0
fi

if   ((percentage < 20)); then step=10
elif ((percentage < 40)); then step=40
elif ((percentage < 60)); then step=60
elif ((percentage < 80)); then step=80
else                           step=100
fi

if [[ "$status" == "Charging" ]]; then
    charging=true
    level=charging
else
    charging=false
    if   ((percentage < 20)); then level=critical
    elif ((percentage < 40)); then level=low
    else                           level=normal
    fi
fi

printf '{"icon":"%s","percentage":"%s%%","status":"%s","level":"%s","charging":%s,"tooltip":"Battery: %s%% (%s)"}\n' \
    "$(battery_icon_path "$step" "$charging")" \
    "$percentage" "$status" "$level" "$charging" "$percentage" "$status"
