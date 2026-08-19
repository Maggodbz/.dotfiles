#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["rich>=13.7"]
# ///
"""Keybindings cheatsheet -- persistent Rich TUI overlay."""

import signal

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Nord palette, matching eww's dark.scss.
NORD = {
    "accent": "#88C0D0",
    "yellow": "#EBCB8B",
    "dim": "#4C566A",
    "fg": "#ECEFF4",
}

KEYBINDINGS = [
    ("SUPER", "Toggle Hyper Mode (press again to exit)"),
    ("", ""),
    ("h / j / k / l", "Move Focus (vim directions)"),
    ("p", "Previous Workspace"),
    ("n", "Next Workspace"),
    ("c", "Close Active Window"),
    ("", ""),
    ("t", "Terminal Overlay"),
    ("a", "App Launcher"),
    ("f", "File Manager Overlay"),
    ("m", "Network Metrics Dashboard"),
    ("b", "Bluetooth Manager"),
    ("i", "Keybindings Cheatsheet (this)"),
    ("SPACE", "Kaya AI Assistant"),
    ("d", "Toggle Mirror Monitors"),
    ("ESCAPE", "Logout Menu (toggle)"),
    ("", ""),
    ("1-9, 0", "Switch to Workspace"),
    ("SHIFT + 1-9, 0", "Move Window to Workspace"),
    ("ALT + h/j/k/l", "Move Window (direction)"),
    ("TAB", "Focus Next Monitor"),
    ("", ""),
    ("F1", "Screenshot -- Full Display"),
    ("F2", "Screenshot -- Active Window"),
    ("F3", "Screenshot -- Region Select"),
]

TABLE_HEIGHT = len(KEYBINDINGS) + 4  # rows + header + panel border + padding


def build_table():
    table = Table(
        show_header=True,
        header_style=f"bold {NORD['accent']}",
        border_style=NORD["dim"],
        expand=False,
        pad_edge=True,
        padding=(0, 3),
    )
    table.add_column("Key", style=f"bold {NORD['yellow']}", min_width=22, justify="center")
    table.add_column("Action", style=NORD["fg"], min_width=42, justify="left")

    for key, action in KEYBINDINGS:
        if key == "" and action == "":
            table.add_row("", "")
        else:
            table.add_row(key, action)

    return Panel(
        table,
        title=Text("Hyper Mode Keybindings", style=f"bold {NORD['fg']}"),
        subtitle=Text("toggle away with [i]  --  overlay stays alive", style="dim"),
        border_style=NORD["accent"],
        padding=(1, 4),
        expand=False,
    )


def main():
    # The overlay is parked on ws42 rather than closed, so it has to survive
    # SIGINT.
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    console = Console()
    console.clear()

    top_pad = max(0, (console.height - TABLE_HEIGHT) // 2)
    console.print("\n" * top_pad, end="")
    console.print(Align.center(build_table()))

    signal.pause()


if __name__ == "__main__":
    main()
