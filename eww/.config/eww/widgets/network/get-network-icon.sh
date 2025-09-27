#!/usr/bin/env bash

connection_info=$(nmcli -t -f NAME,TYPE connection show --active | grep -E "802-11-wireless|ethernet" | head -n1)
connection_name=$(echo "$connection_info" | cut -d: -f1)
connection_type=$(echo "$connection_info" | cut -d: -f2)
wifi_strength=$(iwconfig 2>/dev/null | grep -i quality | head -n1 | sed -E 's/.*Quality=([0-9]+)\/([0-9]+).*/\1 \2/' | awk '{printf "%d", ($1 / $2) * 100}')

[[ "$connection_type" == *"ethernet"* ]] && echo "{\"icon\":\"network-wired-activated\",\"tooltip\":\"Ethernet: $connection_name\"}" && exit
[[ "$connection_type" == *"802-11-wireless"* ]] && {
  [[ -n "$wifi_strength" ]] && {
    [[ "$wifi_strength" -ge 75 ]] && echo "{\"icon\":\"network-wireless-connected-100\",\"tooltip\":\"WiFi: $connection_name ($wifi_strength%)\"}" && exit
    [[ "$wifi_strength" -ge 50 ]] && echo "{\"icon\":\"network-wireless-connected-75\",\"tooltip\":\"WiFi: $connection_name ($wifi_strength%)\"}" && exit
    [[ "$wifi_strength" -ge 25 ]] && echo "{\"icon\":\"network-wireless-connected-50\",\"tooltip\":\"WiFi: $connection_name ($wifi_strength%)\"}" && exit
    echo "{\"icon\":\"network-wireless-connected-25\",\"tooltip\":\"WiFi: $connection_name ($wifi_strength%)\"}" && exit
  }
  echo "{\"icon\":\"network-wireless-connected-75\",\"tooltip\":\"WiFi: $connection_name\"}" && exit
}
echo "{\"icon\":\"network-offline\",\"tooltip\":\"No network connection\"}" 