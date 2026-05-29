"""Command execution and safety classification."""

from __future__ import annotations

import subprocess

SAFE_PREFIXES = (
    "ls", "cat", "head", "tail", "grep", "rg", "find", "wc", "file", "stat",
    "which", "echo", "date", "uptime", "df", "du", "ps", "free", "uname",
    "hyprctl clients", "hyprctl monitors", "hyprctl activewindow",
    "hyprctl workspaces", "hyprctl devices", "ollama list",
    "pip list", "pip show", "npm list", "pwd", "whoami", "hostname",
    "ip addr", "ip link", "ss ", "nmcli", "bluetoothctl info",
    "bluetoothctl devices", "pactl list", "wpctl status",
)

TIMEOUT = 30


def is_safe(cmd: str) -> bool:
    stripped = cmd.strip()
    return any(stripped.startswith(p) for p in SAFE_PREFIXES)


def run(cmd: str) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=TIMEOUT,
        )
        out = r.stdout.strip()
        err = r.stderr.strip()
        combined = out if out else err
        return r.returncode == 0, combined[:3000]
    except subprocess.TimeoutExpired:
        return False, f"Command timed out ({TIMEOUT}s)."
    except Exception as exc:
        return False, str(exc)
