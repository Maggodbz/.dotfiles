#!/usr/bin/env bash
if nmcli -t -f ACTIVE,NAME connection show | grep -q '^yes:enliteai'; then
  echo "on"
else
  echo "off"
fi 