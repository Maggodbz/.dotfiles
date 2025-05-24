#!/usr/bin/env bash
#
# workspace-overview.sh — show workspaces with icons in Waybar

# ensure a sane PATH for Waybar’s environment
PATH=/usr/bin:/bin

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

# collect one icon per unique (workspace, class)
while read -r win; do
    ws=$(jq -r '.workspace.id' <<<"$win")
    cls=$(jq -r '.class'        <<<"$win")
    key="$ws:$cls"
    [[ -n "${seen[$key]}" ]] && continue
    seen[$key]=1

    icon=$(get_icon "$cls")
    icons_per_ws[$ws]+="<img src=\"$icon\"/> "
done < <(/usr/bin/hyprctl clients -j 2>/dev/null | /usr/bin/jq -c '.[]')

# sorted list of workspace IDs
mapfile -t wsids < <(
    /usr/bin/hyprctl workspaces -j |
    /usr/bin/jq -r '.[].id' |
    sort -n
)

# build the output line
out=""
for ws in "${wsids[@]}"; do
    icons="${icons_per_ws[$ws]:-"(empty)"}"
    out+="<span>$ws: $icons</span> │ "
done

# print without trailing separator
echo "${out%│ }"