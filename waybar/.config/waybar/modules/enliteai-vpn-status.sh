#!/bin/bash

# Function to check if VPN is connected
is_vpn_connected() {
  nmcli -t -f ACTIVE,NAME connection show | grep '^yes:enliteai' &>/dev/null
}

# Toggle VPN connection
toggle_vpn() {
  if is_vpn_connected; then
    nmcli connection down enliteai
  else
    nmcli connection up enliteai
  fi
}

# Handle command based on argument
if [[ "$1" == "toggle" ]]; then
  toggle_vpn
else
  # Output status for waybar
  if is_vpn_connected; then
    echo '{"text":" 🟢","tooltip":"enliteAI VPN: connected"}'
  else
    echo '{"text":" 🔴","tooltip":"enliteAI VPN: disconnected"}'
  fi
fi 