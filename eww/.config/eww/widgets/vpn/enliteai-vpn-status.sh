#!/usr/bin/env bash

ip link show | grep -q 'tun[0-9]\|vpn[0-9]\|wg[0-9]' && echo "security-high" || echo "network-offline"