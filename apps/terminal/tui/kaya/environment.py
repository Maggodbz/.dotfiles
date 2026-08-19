"""Runtime environment checks: Python dependencies and GPU availability.

Deliberately stdlib-only so it can be imported and run before the heavier
third-party packages (textual, numpy, …) are known to be present.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess

# What Kaya needs just to render and chat. Voice deps are checked separately and
# are optional — the app degrades gracefully without them.
CORE_DEPS = ("textual", "rich", "numpy")
VOICE_DEPS = ("sounddevice", "faster_whisper", "kokoro_onnx")


def _missing(mods: tuple[str, ...]) -> list[str]:
    return [m for m in mods if importlib.util.find_spec(m) is None]


def missing_core() -> list[str]:
    """Core packages that are not importable. Empty list means good to go."""
    return _missing(CORE_DEPS)


def missing_voice() -> list[str]:
    return _missing(VOICE_DEPS)


def gpu_status() -> tuple[bool, str]:
    """Return (has_gpu, summary).

    "GPU" means an NVIDIA card usable by Ollama for fast local inference. Kaya
    itself runs fine without one, but the model falls back to CPU and is slow,
    which is worth telling the user about.
    """
    smi = shutil.which("nvidia-smi")
    if not smi:
        return False, "no NVIDIA GPU — the model runs on CPU (slow)"
    try:
        proc = subprocess.run(
            [smi, "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        line = proc.stdout.strip().splitlines()[0].strip() if proc.stdout else ""
        if proc.returncode == 0 and line:
            return True, line
    except Exception:
        pass
    return False, "nvidia-smi present but not responding — assuming CPU"
