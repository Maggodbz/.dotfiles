"""Entry point: python3 -m kaya"""

from __future__ import annotations

import atexit
import os
import signal

from . import agent
from .app import KayaApp

# Closing the terminal window kills us with a signal rather than unwinding the
# app, so these have to be handled explicitly or Ollama keeps the model pinned.
_EXIT_SIGNALS = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)


def _handle_exit_signal(signum: int, _frame) -> None:
    agent.unload_all(timeout=2.0)
    os._exit(128 + signum)


def _install_signal_handlers() -> None:
    for sig in _EXIT_SIGNALS:
        try:
            signal.signal(sig, _handle_exit_signal)
        except (OSError, ValueError):
            pass


def main() -> None:
    atexit.register(agent.unload_all)
    _install_signal_handlers()

    app = KayaApp()
    try:
        app.run()
    finally:
        agent.unload_all(timeout=2.0)


if __name__ == "__main__":
    main()
