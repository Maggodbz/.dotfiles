#!/usr/bin/env bash
# Nord icon theme: the single source of truth for every icon the bar draws.
#
# Two consumers, one file:
#   - shell widgets `source` it and call the *_icon_path helpers
#   - eww reads the same values as JSON via `icons.sh --json` (see eww.yuck)
#
# so yuck and bash can never drift apart. Widgets must never name an icon file
# themselves: they report a state ("muted", "critical", a window class) and the
# theme decides which file that is. Icon sets disagree about file names as much
# as they do about directories, so a theme that only remapped directories would
# swap to a bar full of missing icons.
#
# Swap themes by repointing the theme/current symlink, then `eww reload`.

app_dir="/usr/share/icons/Numix-Circle/48/apps"
status_dir="/usr/share/icons/breeze-dark/status/24"
action_dir="/usr/share/icons/breeze-dark/actions/22"

ICON_SIZE=20
WORKSPACE_ICON_SIZE=22
OVERLAY_ICON_SIZE=18

CLOCK_ICON="$action_dir/clock.svg"
BRIGHTNESS_ICON="$action_dir/brightness-low.svg"
DEFAULT_APP_ICON="$app_dir/application-default-icon.svg"

# Directory the fuzzy fallback in get_workspaces.sh searches.
APP_ICON_DIR="$app_dir"

# Window class -> icon file name.
declare -A APP_ICONS=(
    [firefox]=firefox
    [code]=visual-studio-code
    [persistent-term]=terminal
    [wofi]=app-launcher
    [yazi-overlay]=file-manager
    [netmetrics-overlay]=utilities-system-monitor
    [keybindings-overlay]=preferences-desktop-keyboard-shortcuts
    [bluetooth-overlay]=bluetooth-active
    [kaya-overlay]=agent
)

# app_icon_path <window-class> -> path, non-zero when the class is unmapped.
app_icon_path() {
    local name=${APP_ICONS[${1,,}]:-}
    [[ -n $name ]] || return 1
    echo "$app_dir/$name.svg"
}

# volume_icon_path <muted|low|medium|high>
volume_icon_path() {
    echo "$status_dir/audio-volume-$1.svg"
}

# battery_icon_path <0|20|40|60|80|100> <true|false charging>
battery_icon_path() {
    local step
    printf -v step '%03d' "$1"
    [[ $2 == true ]] && echo "$status_dir/battery-$step-charging.svg" \
                     || echo "$status_dir/battery-$step.svg"
}

# Only when run directly, never when sourced: hand the values to eww. Sizes and
# the icons that never change state are all yuck needs; stateful icons arrive as
# full paths from the widget scripts, which source this same file.
if [[ "${BASH_SOURCE[0]}" == "$0" && "${1:-}" == "--json" ]]; then
    printf '{"clock":"%s","brightness":"%s","icon_size":%s,"workspace_icon_size":%s,"overlay_icon_size":%s}\n' \
        "$CLOCK_ICON" "$BRIGHTNESS_ICON" \
        "$ICON_SIZE" "$WORKSPACE_ICON_SIZE" "$OVERLAY_ICON_SIZE"
fi
