"""Local speech-to-text: microphone capture, energy VAD, faster-whisper.

Whisper runs on the CPU (int8) on purpose — the LLM already owns the GPU, and
transcription of a short utterance is fast enough there. Capture is gated by a
simple self-calibrating energy VAD: it waits for you to start talking, then
ends the turn after a short trailing silence, so you never press-and-hold.

Degrades gracefully: if the engine or a mic is missing, talk mode reports why
and Kaya stays a working text chat.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable

import numpy as np

from .voice import _spectrum

RATE = 16000
BLOCK = 512  # 32 ms at 16 kHz

STT_MODEL = os.environ.get("KAYA_STT_MODEL", "base.en")
STT_DIR = Path(
    os.environ.get("KAYA_STT_DIR") or Path.home() / ".local/share/kaya/whisper"
)

LevelCallback = Callable[[float, np.ndarray], None]


class Listener:
    """Captures one spoken utterance at a time and transcribes it."""

    def __init__(self, on_level: LevelCallback | None = None) -> None:
        self._on_level = on_level
        self._model = None
        self._load_lock = threading.Lock()
        self.model_size = STT_MODEL
        self.status = "not loaded"

    # ── availability ─────────────────────────────────────────────

    def _missing(self) -> str | None:
        try:
            import sounddevice  # noqa: F401
        except (ImportError, OSError):
            return "sounddevice not installed (pip install --user sounddevice)"
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return "faster-whisper not installed (pip install --user faster-whisper)"
        return None

    @property
    def available(self) -> bool:
        return self._missing() is None

    def load(self) -> bool:
        """Load the Whisper model. Slow on first call; run it in a worker."""
        problem = self._missing()
        if problem:
            self.status = problem
            return False
        with self._load_lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                threads = max(2, (os.cpu_count() or 4) // 2)
                # Offline-first: use the local cache and never phone home once
                # the model is present. Only the first ever load downloads it.
                for local_only in (True, False):
                    try:
                        self._model = WhisperModel(
                            self.model_size,
                            device="cpu",
                            compute_type="int8",
                            download_root=str(STT_DIR),
                            cpu_threads=threads,
                            local_files_only=local_only,
                        )
                        break
                    except Exception as exc:
                        if local_only:
                            continue  # not cached yet — allow one download
                        self.status = f"model load failed: {exc}"
                        return False
        self.status = f"ready ({self.model_size})"
        return True

    # ── capture ──────────────────────────────────────────────────

    def record_until(
        self,
        stop: threading.Event,
        cancel: threading.Event,
        *,
        max_seconds: float = 120.0,
    ) -> np.ndarray | None:
        """Record from `stop` being set (push-to-stop). Returns 16k mono float32.

        Recording runs until you set `stop` (submit) or `cancel` (discard) —
        there is no silence detection, you decide when the turn ends. `cancel`
        or an empty capture returns None.
        """
        import sounddevice as sd

        max_blocks = int(max_seconds * RATE / BLOCK)
        captured: list[np.ndarray] = []
        floor = 0.006  # only used to scale the level meter

        try:
            stream = sd.InputStream(
                samplerate=RATE, channels=1, dtype="float32", blocksize=BLOCK
            )
        except Exception as exc:
            self.status = f"mic unavailable: {exc}"
            return None

        with stream:
            while not stop.is_set() and not cancel.is_set():
                block, _ = stream.read(BLOCK)
                block = block[:, 0]

                if self._on_level is not None:
                    rms = float(np.sqrt(np.mean(block**2)) + 1e-9)
                    level = float(np.clip((rms - floor) * 12.0, 0.0, 1.0))
                    try:
                        self._on_level(level, _spectrum(block, RATE))
                    except Exception:
                        pass

                captured.append(block)
                if len(captured) >= max_blocks:
                    break

        if cancel.is_set() or not captured:
            return None
        audio = np.concatenate(captured).astype(np.float32)
        if audio.size < int(0.2 * RATE):  # a fraction of a second — treat as empty
            return None
        return audio

    # ── transcription ────────────────────────────────────────────

    def transcribe(self, audio: np.ndarray) -> str:
        if not self.load():
            return ""
        try:
            segments, _ = self._model.transcribe(
                audio,
                beam_size=1,
                language="en",
                vad_filter=True,
                condition_on_previous_text=False,
            )
            return " ".join(s.text.strip() for s in segments).strip()
        except Exception as exc:
            self.status = f"transcription failed: {exc}"
            return ""
