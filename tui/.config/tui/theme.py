"""Shared Nord theme and helpers for all TUI overlays."""

import signal
import subprocess
import sys
import threading
from typing import Callable

from rich.align import Align
from rich.console import RenderableType
from rich.panel import Panel
from rich.text import Text


# Nord palette — single source of truth matching eww dark.scss
NORD = {
    "accent": "#88C0D0",
    "green": "#A3BE8C",
    "red": "#BF616A",
    "yellow": "#EBCB8B",
    "dim": "#4C566A",
    "fg": "#ECEFF4",
    "fg_dim": "#D8DEE9",
    "bg": "#2E3440",
}


def overlay_panel(content: RenderableType, title: str, subtitle: str = "") -> Panel:
    """Wrap content in a consistently-styled outer panel."""
    kw = {}
    if subtitle:
        kw["subtitle"] = Text(subtitle, style="dim")
    return Panel(
        Align.center(content),
        title=Text(title, style=f"bold {NORD['fg']}"),
        border_style=NORD["accent"],
        padding=(1, 2),
        expand=True,
        **kw,
    )


def run(cmd: str, timeout: int = 5) -> tuple[int, str]:
    """Run a shell command and return (exit_code, stdout)."""
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return r.returncode, r.stdout.strip()
    except subprocess.TimeoutExpired:
        return 1, ""
    except Exception:
        return 1, ""


def ignore_sigint() -> None:
    """Ignore SIGINT so the overlay survives being parked on ws42."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def listen_for_keys(
    handlers: dict[str, Callable[[], None]],
    quit_event: threading.Event,
) -> threading.Thread:
    """Spawn a daemon thread that reads single keypresses and dispatches them.

    `handlers` maps single characters to callables.
    The thread sets `quit_event` and exits when the "q" handler fires
    (include "q" in handlers if you want quit, or it auto-quits on "q").
    """

    def _loop():
        try:
            import termios
            import tty

            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setcbreak(fd)
                while not quit_event.is_set():
                    ch = sys.stdin.read(1)
                    if ch.lower() == "q" and "q" not in handlers:
                        quit_event.set()
                        return
                    handler = handlers.get(ch.lower())
                    if handler:
                        handler()
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except (Exception, OSError, ValueError):
            quit_event.wait()

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t
