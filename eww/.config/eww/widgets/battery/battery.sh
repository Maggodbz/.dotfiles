#!/usr/bin/env bash

battery_path=""
[[ -e "/sys/class/power_supply/BAT1" ]] && battery_path="/sys/class/power_supply/BAT1"
[[ -e "/sys/class/power_supply/BAT0" ]] && battery_path="/sys/class/power_supply/BAT0"

[[ -z "$battery_path" ]] && echo '{"icon_name":"battery-060","percentage":"N/A","status":"Unknown","style":"","charging":false,"tooltip":"No battery found"}' && exit

percentage=$(cat "$battery_path/capacity" 2>/dev/null || echo "N/A")
status=$(cat "$battery_path/status" 2>/dev/null || echo "Unknown")

[[ "$status" == "Charging" ]] && {
  [[ "$percentage" -lt 20 ]] && icon="battery-010-charging" && style="color: #A3BE8C;" && echo "{\"icon_name\":\"$icon\",\"percentage\":\"${percentage}%\",\"status\":\"$status\",\"style\":\"$style\",\"charging\":true,\"tooltip\":\"Battery: ${percentage}% ($status)\"}" && exit
  [[ "$percentage" -lt 40 ]] && icon="battery-040-charging" && style="color: #A3BE8C;" && echo "{\"icon_name\":\"$icon\",\"percentage\":\"${percentage}%\",\"status\":\"$status\",\"style\":\"$style\",\"charging\":true,\"tooltip\":\"Battery: ${percentage}% ($status)\"}" && exit
  [[ "$percentage" -lt 60 ]] && icon="battery-060-charging" && style="color: #A3BE8C;" && echo "{\"icon_name\":\"$icon\",\"percentage\":\"${percentage}%\",\"status\":\"$status\",\"style\":\"$style\",\"charging\":true,\"tooltip\":\"Battery: ${percentage}% ($status)\"}" && exit
  [[ "$percentage" -lt 80 ]] && icon="battery-080-charging" && style="color: #A3BE8C;" && echo "{\"icon_name\":\"$icon\",\"percentage\":\"${percentage}%\",\"status\":\"$status\",\"style\":\"$style\",\"charging\":true,\"tooltip\":\"Battery: ${percentage}% ($status)\"}" && exit
  icon="battery-100-charging" && style="color: #A3BE8C;" && echo "{\"icon_name\":\"$icon\",\"percentage\":\"${percentage}%\",\"status\":\"$status\",\"style\":\"$style\",\"charging\":true,\"tooltip\":\"Battery: ${percentage}% ($status)\"}" && exit
}

[[ "$percentage" -lt 20 ]] && icon="battery-010" && style="color: #BF616A;" && echo "{\"icon_name\":\"$icon\",\"percentage\":\"${percentage}%\",\"status\":\"$status\",\"style\":\"$style\",\"charging\":false,\"tooltip\":\"Battery: ${percentage}% ($status)\"}" && exit
[[ "$percentage" -lt 40 ]] && icon="battery-040" && style="color: #EBCB8B;" && echo "{\"icon_name\":\"$icon\",\"percentage\":\"${percentage}%\",\"status\":\"$status\",\"style\":\"$style\",\"charging\":false,\"tooltip\":\"Battery: ${percentage}% ($status)\"}" && exit
[[ "$percentage" -lt 60 ]] && icon="battery-060" && style="" && echo "{\"icon_name\":\"$icon\",\"percentage\":\"${percentage}%\",\"status\":\"$status\",\"style\":\"$style\",\"charging\":false,\"tooltip\":\"Battery: ${percentage}% ($status)\"}" && exit
[[ "$percentage" -lt 80 ]] && icon="battery-080" && style="" && echo "{\"icon_name\":\"$icon\",\"percentage\":\"${percentage}%\",\"status\":\"$status\",\"style\":\"$style\",\"charging\":false,\"tooltip\":\"Battery: ${percentage}% ($status)\"}" && exit
icon="battery-100" && style="" && echo "{\"icon_name\":\"$icon\",\"percentage\":\"${percentage}%\",\"status\":\"$status\",\"style\":\"$style\",\"charging\":false,\"tooltip\":\"Battery: ${percentage}% ($status)\"}"