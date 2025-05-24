#!/usr/bin/env bash

# Kill any existing eww daemon
eww kill

# Start the daemon
eww daemon

# Give it a moment to start up
sleep 0.5

# Open all windows
eww open weather
eww open spotify
eww open apps
eww open audio
eww open screen
eww open profile
eww open more

echo "Eww topbar components started!" 