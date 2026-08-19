#!/usr/bin/env bash
# Enable/disable the laptop's internal panel when the lid opens/closes.
#
# The internal display is auto-detected by connector name (eDP/LVDS/DSI) so this
# works on any laptop without hardcoding "eDP-1". On a desktop with no such
# panel it simply does nothing.
#
#   lid.sh close   # lid shut  -> turn the internal panel off
#   lid.sh open    # lid raised -> turn it back on
export PATH="$HOME/.local/bin:$PATH"

action="$1"

internal=$(
    hyprctl monitors all -j 2>/dev/null \
        | jq -r '.[] | select(.name | test("^(eDP|LVDS|DSI)")) | .name' \
        | head -n1
)

[ -z "$internal" ] && exit 0

case "$action" in
    close) hyprctl keyword monitor "$internal, disable" ;;
    open) hyprctl keyword monitor "$internal, preferred, auto, auto" ;;
    *)
        echo "usage: lid.sh open|close" >&2
        exit 1
        ;;
esac
