#!/bin/bash

# Check if any VPN is connected and get info
get_vpn_status() {
  # Check if any VPN is connected (tun interfaces exist)
  if ip link show | grep -q 'tun[0-9]\|vpn[0-9]\|wg[0-9]'; then
    connected=true
  else
    connected=false
  fi
  
  # Get all active connections
  connections=$(nmcli -t -f NAME,TYPE,DEVICE connection show --active | grep -E 'vpn|wireguard|openvpn|tun' | tr ':' ' ' || echo "No VPN connections")
  
  # Format the tooltip with details
  if [[ "$connections" == "No VPN connections" ]]; then
    tooltip="No active VPN connections"
  else
    tooltip="Active VPN connections:\\n"
    while IFS= read -r line; do
      name=$(echo "$line" | awk '{print $1}')
      type=$(echo "$line" | awk '{print $2}')
      device=$(echo "$line" | awk '{print $3}')
      tooltip+="• $name ($type) on $device\\n"
    done <<< "$connections"
  fi
  
  # Output as JSON
  if $connected; then
    echo "{\"text\":\" Connected\",\"tooltip\":\"$tooltip\",\"icon\":\"vpn-on\"}"
  else
    echo "{\"text\":\" Disconnected\",\"tooltip\":\"$tooltip\",\"icon\":\"vpn-off\"}"
  fi
}

# Output status
get_vpn_status 