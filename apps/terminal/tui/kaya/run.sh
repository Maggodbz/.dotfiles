#!/usr/bin/env bash
# Launch Kaya with the project's interpreter.
#
#   run.sh [args...]
#
# Prefers the uv-managed venv (see setup-env.sh). Falls back to system python3
# so Kaya can still print setup instructions if the env is missing.
export PATH="$HOME/.local/bin:$PATH"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$(dirname "$HERE")${PYTHONPATH:+:$PYTHONPATH}"

VENV="${KAYA_VENV:-$HOME/.local/share/kaya/venv}"
if [ -x "$VENV/bin/python" ]; then
    PY="$VENV/bin/python"
else
    PY="$(command -v python3 || echo /usr/bin/python3)"
fi

exec "$PY" -m kaya "$@"
