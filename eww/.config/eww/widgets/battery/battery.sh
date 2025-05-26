#!/bin/bash

# Get battery path - prefer BAT1 first, fallback to BAT0
BATTERY_PATH=""
if [ -e "/sys/class/power_supply/BAT1" ]; then
    BATTERY_PATH="/sys/class/power_supply/BAT1"
elif [ -e "/sys/class/power_supply/BAT0" ]; then
    BATTERY_PATH="/sys/class/power_supply/BAT0"
fi

# Default values
ICON_NAME="battery-good"
PERCENTAGE="N/A"
STATUS="Unknown"
STYLE=""
CLASS="battery"

if [ -n "$BATTERY_PATH" ]; then
    # Get battery percentage
    PERCENTAGE=$(cat "$BATTERY_PATH/capacity" 2>/dev/null || echo "N/A")
    
    # Get battery status
    STATUS=$(cat "$BATTERY_PATH/status" 2>/dev/null || echo "Unknown")
    
    # Set icon based on status and percentage
    if [ "$STATUS" = "Charging" ]; then
        if [ "$PERCENTAGE" -lt 20 ]; then
            ICON_NAME="battery-caution-charging"
        elif [ "$PERCENTAGE" -lt 40 ]; then
            ICON_NAME="battery-low-charging"
        elif [ "$PERCENTAGE" -lt 80 ]; then
            ICON_NAME="battery-good-charging"
        else
            ICON_NAME="battery-full-charging"
        fi
        STYLE="color: #A3BE8C;" # charging color
    elif [ "$PERCENTAGE" -lt 20 ]; then
        ICON_NAME="battery-caution"
        STYLE="color: #BF616A;" # error-color
    elif [ "$PERCENTAGE" -lt 40 ]; then
        ICON_NAME="battery-low"
        STYLE="color: #EBCB8B;" # warning-color
    elif [ "$PERCENTAGE" -lt 80 ]; then
        ICON_NAME="battery-good"
    else
        ICON_NAME="battery-full"
    fi
    
    # Add percentage symbol
    PERCENTAGE="${PERCENTAGE}%"
fi

# Output JSON for eww
echo "{ \
\"icon_name\": \"$ICON_NAME\", \
\"percentage\": \"$PERCENTAGE\", \
\"status\": \"$STATUS\", \
\"style\": \"$STYLE\", \
\"tooltip\": \"Battery: $PERCENTAGE ($STATUS)\" \
}"