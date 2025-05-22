#!/bin/bash

# Create a temporary file for the keybindings
KEYBINDINGS_FILE=$(mktemp)

# Write keybindings to the file
cat > "$KEYBINDINGS_FILE" << EOF
SUPER                 Toggle Hyper Mode (press again to exit)
[Hyper Mode Active]
h/j/k/l               Move Focus (vim directions)
p                     Previous Workspace
n                     Next Workspace
c                     Close Active Window
t                     Open Terminal Overlay
a                     Open App Launcher
f                     Open File Manager Overlay
i                     Show This Keybindings Cheatsheet
1-9,0                 Switch to Workspace
SHIFT + 1-9,0         Move Window to Workspace
EOF

# Display using wofi
wofi --dmenu \
    --no-actions \
    --insensitive \
    --prompt "Keybindings" \
    --hide-search \
    --key-up "k" \
    --key-down "j" \
    --normal-window \
    --class "keybindings-cheatsheet" \
    < "$KEYBINDINGS_FILE" > /dev/null

# Clean up
rm "$KEYBINDINGS_FILE" 