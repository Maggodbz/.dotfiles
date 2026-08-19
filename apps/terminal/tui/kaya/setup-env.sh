#!/usr/bin/env bash
# Create (or refresh) the uv-managed virtualenv that Kaya runs in. Idempotent —
# safe to re-run to pick up new dependencies. The other TUIs need no setup: they
# declare their deps inline (PEP 723) and uv builds their env on first launch.
#
#   setup-env.sh            # core: text chat + TUIs
#   setup-env.sh --voice    # also install speech (TTS/STT)
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${KAYA_VENV:-$HOME/.local/share/kaya/venv}"

if ! command -v uv >/dev/null 2>&1; then
    cat >&2 <<'EOF'
uv is not installed. Install it, then re-run this script:

    curl -LsSf https://astral.sh/uv/install.sh | sh
EOF
    exit 1
fi

extras=()
if [ "${1:-}" = "--voice" ]; then
    extras=(--extra voice)
fi

echo "› creating virtualenv at $VENV"
uv venv "$VENV"

echo "› installing dependencies${extras:+ (with voice)}"
uv pip install --python "$VENV/bin/python" -r "$HERE/pyproject.toml" "${extras[@]}"

cat <<EOF

Kaya environment ready.
  interpreter: $VENV/bin/python
  launch:      SUPER then SPACE   (or ~/.config/kaya/run.sh)
EOF

if [ ${#extras[@]} -eq 0 ]; then
    echo
    echo "Voice was not installed. Add it later with: $HERE/setup-env.sh --voice"
    echo "Voice also needs the Kokoro model in ~/.local/share/kaya/kokoro/ (see README)."
fi
