#!/usr/bin/env bash
#
# Bootstrap these dotfiles on a fresh Fedora + Hyprland machine. Re-runnable.
#
#   ./install.sh        packages, font, symlinks, Kaya env
#   ./install.sh stow   only re-link the configs into $HOME
#
set -euo pipefail
cd "$(dirname "$0")"


# ─── what gets installed ─────────────────────────────────────────────────────

DNF_PACKAGES=(
    git stow zsh tmux neovim curl unzip           # base
    jq fd-find fzf bat ripgrep socat bc           # cli tools the configs call
    wl-clipboard brightnessctl playerctl xdg-utils
    bluez NetworkManager wireless-tools nmap-ncat # bluetooth / netmetrics widgets
    pipewire wireplumber pipewire-pulseaudio      # wpctl + pactl
    numix-icon-theme-circle breeze-icon-theme     # topbar icons
)

# The Hyprland world is not in Fedora proper.
COPR_REPO=solopasha/hyprland
COPR_PACKAGES=(hyprland hyprpaper hyprshot eww wofi wlogout wezterm yazi)

FONT_NAME="JetBrainsMono Nerd Font"
FONT_URL=https://github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.zip

# Flat stow packages: the package root IS the contents of ~/.config/<name>.
TUI_APPS=(nvim yazi kaya bluetooth-manager netmetrics keybindings)


# ─── helpers ─────────────────────────────────────────────────────────────────

step() { printf '\n▸ %s\n' "$*"; }

# stow_to <target-dir> <packages-parent-dir> <package>...
stow_to() {
    local target=$1 parent=$2
    shift 2
    mkdir -p "$target"
    stow -R -d "$parent" -t "$target" "$@"
}

# Earlier layouts pointed ~/.config/hypr and ~/.config/eww straight at the repo
# with a single symlink. stow needs a real directory to populate.
remove_legacy_links() {
    local path
    for path in "$@"; do
        if [ -L "$path" ]; then
            rm "$path"
        fi
    done
}


# ─── symlinking ──────────────────────────────────────────────────────────────

link_window_manager() {
    stow_to ~/.config/hypr window-manager hypr
}

link_desktop_shell() {
    stow_to ~/.config/eww           desktop-shell topbar
    stow_to ~/.config/hyprpaper     desktop-shell hyprpaper
    stow_to ~/.config/desktop-shell desktop-shell session
}

link_apps() {
    # Home-root configs: ~/.wezterm.lua, ~/.zshrc, ~/.tmux.conf
    stow_to ~ apps/gui         wezterm
    stow_to ~ apps/terminal/cli zsh tmux

    stow_to ~/.config/wofi apps/gui wofi

    local app
    for app in "${TUI_APPS[@]}"; do
        stow_to ~/.config/"$app" apps/terminal/tui "$app"
    done
}

link_configs() {
    step "Linking configs into ~"
    remove_legacy_links ~/.config/hypr ~/.config/eww
    link_window_manager
    link_desktop_shell
    link_apps
}


# ─── installation steps ──────────────────────────────────────────────────────

install_packages() {
    step "Installing Fedora packages"
    sudo dnf install -y "${DNF_PACKAGES[@]}"

    step "Installing the Hyprland stack from $COPR_REPO"
    sudo dnf copr enable -y "$COPR_REPO"
    sudo dnf install -y "${COPR_PACKAGES[@]}"
}

install_uv() {
    command -v uv >/dev/null && return

    step "Installing uv"
    curl -LsSf https://astral.sh/uv/install.sh | sh
}

install_font() {
    fc-list | grep -q "$FONT_NAME" && return

    step "Installing $FONT_NAME"
    local zip=/tmp/jetbrains-mono-nerd-font.zip
    curl -fLsS -o "$zip" "$FONT_URL"
    mkdir -p ~/.local/share/fonts
    unzip -oq "$zip" -d ~/.local/share/fonts
    fc-cache -f
}

setup_kaya_env() {
    step "Building Kaya's Python environment"
    ~/.config/kaya/setup-env.sh --voice
}

print_next_steps() {
    cat <<'EOF'

Done — log into Hyprland, the topbar starts itself.

Still manual — Ollama is a separate daemon, not part of Kaya's uv venv:
  https://ollama.com   then:   ollama pull gemma4:e2b
EOF
}


# ─── entry point ─────────────────────────────────────────────────────────────

main() {
    case "${1:-all}" in
        all)
            install_packages
            install_uv
            install_font
            link_configs
            setup_kaya_env
            print_next_steps
            ;;
        stow)
            link_configs
            ;;
        *)
            echo "usage: ${0##*/} [all|stow]" >&2
            exit 1
            ;;
    esac
}

main "$@"
