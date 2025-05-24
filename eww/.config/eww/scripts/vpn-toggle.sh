#!/usr/bin/env bash
if nmcli -t -f ACTIVE,NAME connection show | grep -q '^yes:enliteai'; then
  nmcli connection down enliteai
else
  nmcli connection up   enliteai
fi 