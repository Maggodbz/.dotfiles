#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Network Live Metrics Dashboard
# Displays VPN, SSH, and Kubernetes status in a live-refreshing TUI
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Colors ───────────────────────────────────────────────────────────────────
RESET="\033[0m"
BOLD="\033[1m"
DIM="\033[2m"
GREEN="\033[32m"
RED="\033[31m"
YELLOW="\033[33m"
CYAN="\033[36m"
WHITE="\033[37m"
BG_DARK="\033[48;2;45;47;62m"

# ── Symbols ──────────────────────────────────────────────────────────────────
DOT_ON="●"
DOT_OFF="○"
ARROW="▸"
CHECK="✓"
CROSS="✗"
DASH="─"

# ── State files for async checks ─────────────────────────────────────────────
STATE_DIR=$(mktemp -d /tmp/netmetrics.XXXXXX)
trap 'rm -rf "$STATE_DIR"' EXIT

# ── Helper: draw a horizontal rule ───────────────────────────────────────────
hr() {
    local width=${1:-60}
    printf "  ${DIM}"
    printf '%*s' "$width" '' | tr ' ' "$DASH"
    printf "${RESET}\n"
}

# ── Helper: section header ───────────────────────────────────────────────────
section() {
    printf "\n  ${BOLD}${CYAN}%s${RESET}\n" "$1"
    hr "${2:-60}"
}

# ── Helper: pad string to width ──────────────────────────────────────────────
pad() {
    printf "%-${2}s" "$1"
}

# ── VPN Status ───────────────────────────────────────────────────────────────
get_vpn_status() {
    # nmcli returns NAME:TYPE:DEVICE -- active VPNs have a DEVICE assigned
    while IFS=: read -r name type device; do
        local label status color dot
        case "$type" in
            wireguard) label="WireGuard" ;;
            vpn)       label="OpenVPN"   ;;
            *)         continue          ;;
        esac

        if [[ -n "$device" ]]; then
            status="Connected"
            color="$GREEN"
            dot="$DOT_ON"
        else
            status="Disconnected"
            color="$RED"
            dot="$DOT_OFF"
        fi

        printf "  ${color}${dot}${RESET}  $(pad "$name" 22) ${DIM}$(pad "$label" 12)${RESET} ${color}${BOLD}%s${RESET}\n" "$status"
    done < <(nmcli -t -f NAME,TYPE,DEVICE connection show 2>/dev/null | grep -E 'vpn|wireguard')
}

# ── SSH Host Status ──────────────────────────────────────────────────────────
check_ssh_hosts_async() {
    # Parse ~/.ssh/config for Host entries with their details
    awk '
        /^Host [^*]/ { host=$2; ip=""; port=22; user="" }
        /HostName/   { ip=$2 }
        /Port/       { port=$2 }
        /User/       { user=$2 }
        /^$/         { if(host && ip) print host"|"ip"|"port"|"user; host="" }
        END          { if(host && ip) print host"|"ip"|"port"|"user }
    ' ~/.ssh/config 2>/dev/null | while IFS='|' read -r host ip port user; do
        # Run nc check in background, write result to state file
        (
            if nc -z -w 2 "$ip" "$port" 2>/dev/null; then
                echo "up" > "$STATE_DIR/ssh_${host}"
            else
                echo "down" > "$STATE_DIR/ssh_${host}"
            fi
        ) &
    done
}

get_ssh_status() {
    awk '
        /^Host [^*]/ { host=$2; ip=""; port=22; user="" }
        /HostName/   { ip=$2 }
        /Port/       { port=$2 }
        /User/       { user=$2 }
        /^$/         { if(host && ip) print host"|"ip"|"port"|"user; host="" }
        END          { if(host && ip) print host"|"ip"|"port"|"user }
    ' ~/.ssh/config 2>/dev/null | while IFS='|' read -r host ip port user; do
        local state color dot status target

        if [[ "$port" != "22" ]]; then
            target="${ip}:${port}"
        else
            target="${ip}"
        fi

        state_file="$STATE_DIR/ssh_${host}"
        if [[ -f "$state_file" ]]; then
            state=$(cat "$state_file")
        else
            state="checking"
        fi

        case "$state" in
            up)
                color="$GREEN"; dot="$DOT_ON"; status="Reachable"
                ;;
            down)
                color="$RED"; dot="$DOT_OFF"; status="Unreachable"
                ;;
            *)
                color="$YELLOW"; dot="$DOT_OFF"; status="Checking..."
                ;;
        esac

        printf "  ${color}${dot}${RESET}  $(pad "$host" 22) ${DIM}$(pad "$target" 24)${RESET} ${color}${BOLD}%s${RESET}\n" "$status"
    done
}

# ── Kubernetes Context Status ────────────────────────────────────────────────
check_k8s_contexts_async() {
    local current_ctx
    current_ctx=$(kubectl config current-context 2>/dev/null || echo "")

    kubectl config get-contexts -o name 2>/dev/null | while read -r ctx; do
        (
            if kubectl --context="$ctx" auth can-i get ns --request-timeout=3s >/dev/null 2>&1; then
                echo "ok" > "$STATE_DIR/k8s_${ctx}"
            else
                echo "fail" > "$STATE_DIR/k8s_${ctx}"
            fi
        ) &
    done
}

get_k8s_status() {
    local current_ctx
    current_ctx=$(kubectl config current-context 2>/dev/null || echo "")

    kubectl config get-contexts -o name 2>/dev/null | while read -r ctx; do
        local state color indicator status cluster_name

        # Get cluster name from context (columns shift when * marker is present)
        cluster_name=$(kubectl config get-contexts "$ctx" --no-headers 2>/dev/null \
            | awk '{ if ($1 == "*") print $3; else print $2 }')

        state_file="$STATE_DIR/k8s_${ctx}"
        if [[ -f "$state_file" ]]; then
            state=$(cat "$state_file")
        else
            state="checking"
        fi

        case "$state" in
            ok)   color="$GREEN";  status="${CHECK} Access OK"    ;;
            fail) color="$RED";    status="${CROSS} Unreachable"  ;;
            *)    color="$YELLOW"; status="⟳ Checking..."        ;;
        esac

        if [[ "$ctx" == "$current_ctx" ]]; then
            indicator="${CYAN}${BOLD}${ARROW}${RESET}"
        else
            indicator=" "
        fi

        printf "  ${indicator}  $(pad "$ctx" 22) ${DIM}$(pad "${cluster_name:-$ctx}" 18)${RESET} ${color}${BOLD}%s${RESET}\n" "$status"
    done
}

# ── Title Banner ─────────────────────────────────────────────────────────────
draw_title() {
    local width=60
    local title="NETWORK LIVE METRICS"
    local title_len=${#title}
    local pad_left=$(( (width - title_len) / 2 ))
    local pad_right=$(( width - title_len - pad_left ))

    printf "\n"
    printf "  ${CYAN}╭%s╮${RESET}\n" "$(printf '%*s' "$width" '' | tr ' ' '─')"
    printf "  ${CYAN}│${RESET}%*s${BOLD}${WHITE}%s${RESET}%*s${CYAN}│${RESET}\n" "$pad_left" "" "$title" "$pad_right" ""
    printf "  ${CYAN}╰%s╯${RESET}\n" "$(printf '%*s' "$width" '' | tr ' ' '─')"
}

# ── Footer ───────────────────────────────────────────────────────────────────
draw_footer() {
    local now
    now=$(date '+%H:%M:%S')
    printf "\n"
    hr 60
    printf "  ${DIM}Last refresh: ${now} │ Refreshing every 5s │ q to quit${RESET}\n"
}

# ── Main Render ──────────────────────────────────────────────────────────────
render() {
    clear
    draw_title

    section "VPNs" 60
    get_vpn_status

    section "SSH Hosts" 60
    get_ssh_status

    section "Kubernetes Contexts" 60
    get_k8s_status

    draw_footer
}

# ── Main Loop ────────────────────────────────────────────────────────────────
main() {
    # Hide cursor
    tput civis 2>/dev/null
    trap 'tput cnorm 2>/dev/null; exit 0' EXIT INT TERM

    while true; do
        # Kick off async checks
        check_ssh_hosts_async
        check_k8s_contexts_async

        # Wait a moment for fast checks to complete
        sleep 1

        # Render the dashboard
        render

        # Wait for remaining interval, but allow 'q' to quit
        for _ in $(seq 1 4); do
            if read -rsn1 -t 1 key 2>/dev/null; then
                [[ "$key" == "q" || "$key" == "Q" ]] && exit 0
            fi
        done

        # Wait for all background jobs to finish before next cycle
        wait 2>/dev/null
    done
}

main

