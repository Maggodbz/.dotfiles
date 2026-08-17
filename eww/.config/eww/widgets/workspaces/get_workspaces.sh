#!/bin/bash

# Icon directory - from eww theme settings
ICON_DIR="/usr/share/icons/Numix-Circle/48/apps"
DEFAULT_ICON="$ICON_DIR/application-default-icon.svg"

# Custom icon directory - can be generated from eww variables if needed
CUSTOM_ICON_FILE="$HOME/.config/eww/custom_app_icons.json"

# Check if custom icons file exists
if [ -f "$CUSTOM_ICON_FILE" ]; then
    HAS_CUSTOM_ICONS=true
else
    HAS_CUSTOM_ICONS=false
fi

# lookup an icon for a given window class
get_icon() {
    local class="${1,,}"
    
    # Check for custom icon first
    if [ "$HAS_CUSTOM_ICONS" = true ]; then
        local custom_icon
        custom_icon=$(jq -r ".\"$class\" // empty" "$CUSTOM_ICON_FILE" 2>/dev/null)
        if [ -n "$custom_icon" ] && [ -f "$custom_icon" ]; then
            echo "$custom_icon"
            return
        fi
    fi
    
    # Check for class-specific mappings
    case "$class" in
        "firefox")
            echo "$ICON_DIR/firefox.svg"
            return
            ;;
        "code")
            echo "$ICON_DIR/visual-studio-code.svg"
            return
            ;;
        "persistent-term")
            echo "$ICON_DIR/terminal.svg"
            return
            ;;
        "yazi-overlay")
            echo "$ICON_DIR/file-manager.svg"
            return
            ;;
        "wofi")
            echo "$ICON_DIR/app-launcher.svg"
            return
            ;;
        "netmetrics-overlay")
            echo "$ICON_DIR/utilities-system-monitor.svg"
            return
            ;;
        "keybindings-overlay")
            echo "$ICON_DIR/preferences-desktop-keyboard-shortcuts.svg"
            return
            ;;
        "bluetooth-overlay")
            echo "$ICON_DIR/bluetooth-active.svg"
            return
            ;;
        "jarvis-overlay"|"kaya-overlay")
            echo "$ICON_DIR/agent.svg"
            return
            ;;
    esac
    
    # Fall back to regular icon lookup
    for name in "$class" "${class%-*}" "${class##*.}"; do
        local f
        f=$(find "$ICON_DIR" -iname "*$name*.svg" 2>/dev/null | head -n1)
        [[ -n "$f" ]] && { echo "$f"; return; }
    done
    echo "$DEFAULT_ICON"
}

# associative arrays to hold icons per workspace
declare -A icons_per_ws

# Record the active workspace independently for every monitor. A single global
# "focused workspace" makes every topbar highlight the same workspace.
declare -A active_monitor_per_ws
while IFS=$'\t' read -r ws monitor; do
    active_monitor_per_ws["$ws"]="$monitor"
done < <(
    hyprctl monitors -j 2>/dev/null |
    jq -r '.[] | select(.disabled == false) | [.activeWorkspace.id, .name] | @tsv'
)

# collect icons for all windows
while read -r win; do
    ws=$(jq -r '.workspace.id' <<<"$win")
    cls=$(jq -r '.class' <<<"$win")
    
    icon=$(get_icon "$cls")
    if [ -n "${icons_per_ws[$ws]}" ]; then
        icons_per_ws[$ws]+=",\"$icon\""
    else
        icons_per_ws[$ws]="\"$icon\""
    fi
done < <(hyprctl clients -j 2>/dev/null | jq -c '.[]')

# Get all workspace IDs
mapfile -t all_wsids < <(
    hyprctl workspaces -j |
    jq -r '.[].id' |
    sort -n
)

# Filter out overlay workspace (42) – its icons live in the hyper button
wsids=()
for ws in "${all_wsids[@]}"; do
    if [ "$ws" != "42" ]; then
        wsids+=("$ws")
    fi
done

# build the JSON output
echo -n '{'
echo -n '"workspaces": ['

first=true
for ws in "${wsids[@]}"; do
    if [ "$first" = true ]; then
        first=false
    else
        echo -n ','
    fi
    
    icons="${icons_per_ws[$ws]:-\"\"}"
    if [ "$icons" = "\"\"" ]; then
        icons=""
    fi
    
    active_monitor="${active_monitor_per_ws[$ws]:-}"
    
    display_name="$ws:"
    
    echo -n "{"
    echo -n "\"id\": \"$ws\","
    echo -n "\"display_name\": \"$display_name\","
    echo -n "\"active_monitor\": \"$active_monitor\","
    echo -n "\"icons\": [$icons]"
    echo -n "}"
done

echo -n ']'
echo '}' 