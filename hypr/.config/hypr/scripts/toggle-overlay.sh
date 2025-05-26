#!/bin/bash

# Usage: toggle-overlay.sh <app_class> <launch_command>
# Example: toggle-overlay.sh persistent-term "wezterm start --class persistent-term"
# Example: toggle-overlay.sh yazi-overlay "wezterm start --class yazi-overlay -- bash -c 'yazi'"

# Get parameters
APP_CLASS="$1"
LAUNCH_CMD="$2"

# Define the overlay storage workspace (single workspace for all overlays)
OVERLAY_WORKSPACE="42"

# Exit if no app class provided
if [ -z "$APP_CLASS" ] || [ -z "$LAUNCH_CMD" ]; then
    echo "Usage: toggle-overlay.sh <app_class> <launch_command>"
    exit 1
fi

# Check if our app exists in the overlay workspace
if hyprctl clients -j | jq -e ".[] | select(.class == \"$APP_CLASS\" and .workspace.id == $OVERLAY_WORKSPACE)" > /dev/null; then
    # App exists in overlay workspace, move it to the current workspace
    hyprctl dispatch movetoworkspace "$(hyprctl activeworkspace -j | jq -r '.id'),class:$APP_CLASS"
    
    # Focus the app
    hyprctl dispatch focuswindow "class:$APP_CLASS"
elif hyprctl clients -j | jq -e ".[] | select(.class == \"$APP_CLASS\")" > /dev/null; then
    # App exists on a visible workspace, move it to the overlay workspace
    hyprctl dispatch movetoworkspacesilent "$OVERLAY_WORKSPACE,class:$APP_CLASS"
else
    # No app exists, create a new one with our custom class
    eval "$LAUNCH_CMD"
    
    # Wait for the app to appear
    sleep 0.2
    
    # Set appropriate window rules for the new app
    hyprctl dispatch togglefloating "class:$APP_CLASS"
    hyprctl dispatch resizewindowpixel "exact 1200 700,class:$APP_CLASS"
    hyprctl dispatch centerwindow "class:$APP_CLASS"
fi 