#!/bin/bash

# Icon directory - adjust as needed for your system
ICON_DIR="/usr/share/icons/Numix-Circle/48/apps"
DEFAULT_ICON="$ICON_DIR/application-default-icon.svg"

# lookup an icon for a given window class
get_icon() {
    local class="${1,,}"
    for name in "$class" "${class%-*}" "${class##*.}"; do
        local f
        f=$(find "$ICON_DIR" -iname "*$name*.svg" 2>/dev/null | head -n1)
        [[ -n "$f" ]] && { echo "$f"; return; }
    done
    echo "$DEFAULT_ICON"
}

# associative arrays to hold icons per workspace
declare -A icons_per_ws

# Get active workspace
active_ws=$(hyprctl activewindow -j 2>/dev/null | jq -r '.workspace.id // empty')
if [ -z "$active_ws" ]; then
  active_ws=$(hyprctl monitors -j | jq -r '.[] | select(.focused) | .activeWorkspace.id')
fi

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

# Custom sort: Special workspace (42) first, then the rest in numeric order
wsids=()
for ws in "${all_wsids[@]}"; do
    if [ "$ws" == "42" ]; then
        # Add special workspace to the beginning
        wsids=("$ws" "${wsids[@]}")
    else
        # Add other workspaces to the end
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
    
    is_active="false"
    if [ "$ws" == "$active_ws" ]; then
        is_active="true"
    fi
    
    # Set display name based on workspace ID
    if [ "$ws" == "42" ]; then
        display_name="Special:"
    else
        display_name="$ws:"
    fi
    
    echo -n "{"
    echo -n "\"id\": \"$ws\","
    echo -n "\"display_name\": \"$display_name\","
    echo -n "\"active\": $is_active,"
    echo -n "\"icons\": [$icons]"
    echo -n "}"
done

echo -n ']'
echo '}' 