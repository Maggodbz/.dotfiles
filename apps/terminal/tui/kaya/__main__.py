"""Entry point: python3 -m kaya"""

from __future__ import annotations

import atexit
import os
import signal
import sys

from . import environment

# Closing the terminal window kills us with a signal rather than unwinding the
# app, so these have to be handled explicitly or Ollama keeps the model pinned.
_EXIT_SIGNALS = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)


def _handle_exit_signal(signum: int, _frame) -> None:
    from . import agent

    agent.unload_all(timeout=2.0)
    os._exit(128 + signum)


def _install_signal_handlers() -> None:
    for sig in _EXIT_SIGNALS:
        try:
            signal.signal(sig, _handle_exit_signal)
        except (OSError, ValueError):
            pass


def _print_setup_help(missing: list[str]) -> None:
    venv = os.environ.get(
        "KAYA_VENV", os.path.expanduser("~/.local/share/kaya/venv")
    )
    print(
        "Kaya's Python environment isn't ready.\n\n"
        f"Missing packages: {', '.join(missing)}\n\n"
        "Set it up once with uv:\n\n"
        "    ~/.config/kaya/setup-env.sh            # text chat\n"
        "    ~/.config/kaya/setup-env.sh --voice    # + speech (TTS/STT)\n\n"
        f"That builds a virtualenv at:\n    {venv}\n\n"
        "Then relaunch Kaya (SUPER, then SPACE)."
    )
    # The overlay terminal closes the moment we exit, so hold it open long
    # enough to actually read the message when launched interactively.
    try:
        if sys.stdin.isatty():
            input("\nPress Enter to close… ")
    except (EOFError, KeyboardInterrupt):
        pass


def main() -> None:
    missing = environment.missing_core()
    if missing:
        _print_setup_help(missing)
        return

    # Safe to pull in the heavy UI now that its dependencies are present.
    from . import agent
    from .app import KayaApp

    atexit.register(agent.unload_all)
    _install_signal_handlers()

    app = KayaApp()
    try:
        app.run()
    finally:
        agent.unload_all(timeout=2.0)


if __name__ == "__main__":
    main()
