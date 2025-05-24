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
  # Output status for eww
  if is_vpn_connected; then
    echo '{"text":" 🟢","tooltip":"enliteAI VPN: connected","icon":"vpn-on"}'
  else
    echo '{"text":" 🔴","tooltip":"enliteAI VPN: disconnected","icon":"vpn-off"}'
  fi
fi 