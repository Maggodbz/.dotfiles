#!/usr/bin/env python3
"""Keybindings cheatsheet – persistent Rich TUI for toggle-overlay.sh."""

import signal, sys
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.align import Align
from rich.text import Text

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
    ("i", "Keybindings Cheatsheet (this)"),
    ("d", "Toggle Mirror Monitors"),
    ("ESCAPE", "Logout Menu"),
    ("", ""),
    ("1–9, 0", "Switch to Workspace"),
    ("SHIFT + 1–9, 0", "Move Window to Workspace"),
    ("ALT + h/j/k/l", "Move Window (direction)"),
    ("ALT + ,", "Focus Next Monitor"),
    ("", ""),
    ("F1", "Screenshot – Full Display"),
    ("F2", "Screenshot – Active Window"),
    ("F3", "Screenshot – Region Select"),
]


def build_table() -> Panel:
    table = Table(
        show_header=True,
        header_style="bold cyan",
        border_style="bright_black",
        expand=True,
        pad_edge=True,
        padding=(0, 2),
    )
    table.add_column("Key", style="bold yellow", ratio=1)
    table.add_column("Action", style="white", ratio=3)

    for key, action in KEYBINDINGS:
        if key == "" and action == "":
            table.add_row("", "")  # spacer
        else:
            table.add_row(key, action)

    title = Text("⌨  Hyper Mode Keybindings", style="bold bright_white")
    return Panel(
        Align.center(table),
        title=title,
        subtitle=Text("toggle away with [i]  •  overlay stays alive", style="dim"),
        border_style="bright_cyan",
        padding=(1, 2),
    )


def main():
    # Ignore SIGINT so the overlay stays alive when moved to ws42
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    console = Console()
    console.clear()
    console.print()
    console.print(Align.center(build_table()))
    console.print()

    # Sleep forever – toggle-overlay.sh hides/shows the wezterm window
    signal.pause()


if __name__ == "__main__":
    main()

