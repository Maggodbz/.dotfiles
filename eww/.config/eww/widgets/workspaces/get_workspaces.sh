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

# associative arrays to hold icons per workspace and seen keys
declare -A icons_per_ws
declare -A seen

# Get active workspace
active_ws=$(hyprctl activewindow -j 2>/dev/null | jq -r '.workspace.id // empty')
if [ -z "$active_ws" ]; then
  active_ws=$(hyprctl monitors -j | jq -r '.[] | select(.focused) | .activeWorkspace.id')
fi

# collect one icon per unique (workspace, class)
while read -r win; do
    ws=$(jq -r '.workspace.id' <<<"$win")
    cls=$(jq -r '.class' <<<"$win")
    key="$ws:$cls"
    [[ -n "${seen[$key]}" ]] && continue
    seen[$key]=1

    icon=$(get_icon "$cls")
    if [ -n "${icons_per_ws[$ws]}" ]; then
        icons_per_ws[$ws]+=",\"$icon\""
    else
        icons_per_ws[$ws]="\"$icon\""
    fi
done < <(hyprctl clients -j 2>/dev/null | jq -c '.[]')

# sorted list of workspace IDs
mapfile -t wsids < <(
    hyprctl workspaces -j |
    jq -r '.[].id' |
    sort -n
)

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
    
    echo -n "{"
    echo -n "\"id\": \"$ws\","
    echo -n "\"active\": $is_active,"
    echo -n "\"icons\": [$icons]"
    echo -n "}"
done

echo -n ']'
echo '}' 