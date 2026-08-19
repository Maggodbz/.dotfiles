#!/usr/bin/env bash
# Toggle mirror: all monitors mirror the active one, or restore extended mode.

MIRROR_STATE="/tmp/hypr-mirror-active"

if [[ -f "$MIRROR_STATE" ]]; then
    # Mirroring is on — restore every monitor we saved earlier.
    # We can't rely on `hyprctl monitors -j` here because mirrored
    # monitors may no longer appear in that list.
    while read -r mon; do
        hyprctl keyword monitor "$mon, preferred, auto, 1"
    done < "$MIRROR_STATE"
    rm -f "$MIRROR_STATE"
else
    # Save ALL monitor names before we change anything
    # Use "monitors all" to include disabled monitors (e.g. lid-closed laptop)
    mapfile -t ALL_MONS < <(hyprctl monitors all -j | jq -r '.[].name')

    # Get the currently focused monitor
    ACTIVE=$(hyprctl monitors -j | jq -r '.[] | select(.focused==true) | .name')

    # Mirror every other monitor to the active one
    for mon in "${ALL_MONS[@]}"; do
        [[ "$mon" == "$ACTIVE" ]] && continue
        hyprctl keyword monitor "$mon, preferred, auto, 1, mirror, $ACTIVE"
    done

    # Save all monitor names (one per line) so we can restore them later
    printf '%s\n' "${ALL_MONS[@]}" > "$MIRROR_STATE"
fi

