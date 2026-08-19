#!/usr/bin/env bash

# System Information Tooltip Script (Text Format)
# Returns plain text like the clock tooltip

# Get system info
OS=$(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)
KERNEL=$(uname -r)
UPTIME=$(uptime -p | sed 's/up //')
SHELL=$(basename $SHELL)

# Get hardware info
CPU=$(lscpu | grep "Model name" | cut -d':' -f2 | xargs)
CPU_CORES=$(nproc)
RAM_TOTAL=$(free -h | awk '/^Mem:/ {print $2}')
RAM_USED=$(free -h | awk '/^Mem:/ {print $3}')
RAM_PERCENT=$(free | awk '/^Mem:/ {printf "%.1f", $3/$2 * 100}')

# Get GPU info (NVIDIA)
if command -v nvidia-smi &> /dev/null; then
    GPU=$(nvidia-smi --query-gpu=name --format=csv,noheader,nounits | head -1)
    GPU_TEMP=$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits | head -1)
    GPU_USAGE=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits | head -1)
    GPU_MEM_USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
    GPU_MEM_TOTAL=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
    GPU_MEM_PERCENT=$(echo "scale=1; $GPU_MEM_USED * 100 / $GPU_MEM_TOTAL" | bc -l 2>/dev/null || echo "0")
else
    GPU="Integrated GPU"
    GPU_TEMP="N/A"
    GPU_USAGE="N/A"
    GPU_MEM_PERCENT="N/A"
fi

# Get storage info
STORAGE_USED=$(df -h / | awk 'NR==2 {print $3}')
STORAGE_TOTAL=$(df -h / | awk 'NR==2 {print $2}')
STORAGE_PERCENT=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')

# Get network info
if command -v ip &> /dev/null; then
    NETWORK_INTERFACE=$(ip route | grep default | awk '{print $5}' | head -1)
    if [ -n "$NETWORK_INTERFACE" ]; then
        NETWORK_SPEED=$(cat /sys/class/net/$NETWORK_INTERFACE/speed 2>/dev/null || echo "N/A")
        NETWORK_SPEED="${NETWORK_SPEED}Mbps"
    else
        NETWORK_SPEED="N/A"
    fi
else
    NETWORK_SPEED="N/A"
fi

# Get user and session info
USER=$(whoami)
DESKTOP="Hyprland"
ACTIVE_WINDOWS=$(hyprctl clients | grep -c "Window" 2>/dev/null || echo "0")
CURRENT_WORKSPACE=$(hyprctl activewindow | grep "workspace" | awk '{print $3}' 2>/dev/null || echo "1")

# Get CPU usage
CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//')

# Create text output (like clock tooltip)
cat << EOF
🖥️ System Overview
$OS
Uptime: $UPTIME
Kernel: $KERNEL

⚡ Hardware
CPU: $CPU
CPU Usage: ${CPU_USAGE}%
RAM: $RAM_USED / $RAM_TOTAL ($RAM_PERCENT%)
GPU: $GPU
GPU: ${GPU_USAGE}% @ ${GPU_TEMP}°C
Storage: $STORAGE_USED / $STORAGE_TOTAL ($STORAGE_PERCENT%)

📊 Live Metrics
Network: $NETWORK_SPEED
Active Windows: $ACTIVE_WINDOWS
Workspace: $CURRENT_WORKSPACE
EOF
