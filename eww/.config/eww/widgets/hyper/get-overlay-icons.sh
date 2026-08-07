#!/bin/bash
# Returns JSON array of icon paths for overlay apps parked in workspace 42.

ICON_DIR="/usr/share/icons/Numix-Circle/48/apps"
OVERLAY_WS=42

get_overlay_icon() {
    case "${1,,}" in
        "persistent-term")       echo "$ICON_DIR/terminal.svg" ;;
        "wofi")                  echo "$ICON_DIR/app-launcher.svg" ;;
        "yazi-overlay")          echo "$ICON_DIR/file-manager.svg" ;;
        "netmetrics-overlay")    echo "$ICON_DIR/utilities-system-monitor.svg" ;;
        "keybindings-overlay")   echo "$ICON_DIR/preferences-desktop-keyboard-shortcuts.svg" ;;
        "bluetooth-overlay")     echo "$ICON_DIR/bluetooth-active.svg" ;;
        "jarvis-overlay"|"kaya-overlay") echo "$ICON_DIR/agent.svg" ;;
        *)                       return 1 ;;
    esac
}

icons=()
while read -r cls; do
    icon=$(get_overlay_icon "$cls") && icons+=("\"$icon\"")
done < <(hyprctl clients -j 2>/dev/null | jq -r ".[] | select(.workspace.id == $OVERLAY_WS) | .class")

printf '[%s]' "$(IFS=,; echo "${icons[*]}")"
