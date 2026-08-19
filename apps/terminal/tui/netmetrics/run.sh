#!/usr/bin/env bash
# uv resolves the script's own dependencies (see the PEP 723 header) and caches
# the environment, so there is nothing to set up ahead of time.
export PATH="$HOME/.local/bin:$PATH"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec uv run --script "$HERE/netmetrics-dashboard.py" "$@"
