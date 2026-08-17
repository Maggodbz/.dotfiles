"""Speech synthesis (Kokoro) with a live amplitude feed for the visualiser.

Kokoro runs on the CPU via ONNX Runtime on purpose: the LLM already occupies
almost all of the GPU, so a GPU TTS model would evict it on every reply.

Everything degrades gracefully — if the model or audio stack is missing, Kaya
stays a working text chat and reports why speech is unavailable.
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Callable

import numpy as np

_DEFAULT_DIRS = (
    Path.home() / ".local/share/kaya/kokoro",
    Path.home() / ".local/share/jarvis/kokoro",
)


def _resolve_model_dir() -> Path:
    env = os.environ.get("KAYA_VOICE_DIR") or os.environ.get("JARVIS_VOICE_DIR")
    if env:
        return Path(env)
    for path in _DEFAULT_DIRS:
        if (path / "kokoro-v1.0.onnx").exists():
            return path
    return _DEFAULT_DIRS[0]


MODEL_DIR = _resolve_model_dir()
MODEL_FILE = MODEL_DIR / "kokoro-v1.0.onnx"
VOICES_FILE = MODEL_DIR / "voices-v1.0.bin"
DEFAULT_VOICE = os.environ.get("KAYA_VOICE") or os.environ.get("JARVIS_VOICE", "af_heart")
LANG = os.environ.get("KAYA_VOICE_LANG") or os.environ.get("JARVIS_VOICE_LANG", "en-us")

NUM_BANDS = 16
BLOCK = 1024
MAX_CHUNK_CHARS = 220

LevelCallback = Callable[[float, np.ndarray], None]
StateCallback = Callable[[bool], None]


def split_sentences(text: str) -> list[str]:
    """Chunk a reply so speech starts before the whole thing is synthesised."""
    text = re.sub(r"```.*?```", " code block omitted. ", text, flags=re.S)
    text = re.sub(r"[*_`#>]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    parts = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    for part in parts:
        part = part.strip()
        while len(part) > MAX_CHUNK_CHARS:
            cut = part.rfind(",", 0, MAX_CHUNK_CHARS)
            if cut < MAX_CHUNK_CHARS // 3:
                cut = MAX_CHUNK_CHARS
            chunks.append(part[:cut].strip())
            part = part[cut:].strip()
        if part:
            chunks.append(part)
    return chunks


def _spectrum(block: np.ndarray, rate: int) -> np.ndarray:
    """Log-spaced band energies, normalised to 0..1."""
    if block.size < 32:
        return np.zeros(NUM_BANDS)
    window = block * np.hanning(block.size)
    spec = np.abs(np.fft.rfft(window))
    freqs = np.fft.rfftfreq(block.size, 1.0 / rate)
    edges = np.logspace(np.log10(80.0), np.log10(min(7500.0, rate / 2)), NUM_BANDS + 1)

    bands = np.zeros(NUM_BANDS)
    for i in range(NUM_BANDS):
        sel = (freqs >= edges[i]) & (freqs < edges[i + 1])
        if sel.any():
            bands[i] = float(spec[sel].mean())

    bands = np.log1p(bands * 12.0)
    peak = bands.max()
    return bands / peak if peak > 0 else bands


class Voice:
    """Synthesises speech and streams playback levels to a callback."""

    def __init__(
        self,
        on_level: LevelCallback | None = None,
        on_state: StateCallback | None = None,
    ) -> None:
        self._on_level = on_level
        self._on_state = on_state
        self._kokoro = None
        self._load_lock = threading.Lock()
        self._stop = threading.Event()
        self._muted = False
        self.enabled = True
        self.voice_name = DEFAULT_VOICE
        self.status = "not loaded"

    # ── availability ─────────────────────────────────────────────

    @property
    def installed(self) -> bool:
        return self._missing() is None

    def _missing(self) -> str | None:
        try:
            import kokoro_onnx  # noqa: F401
        except ImportError:
            return "kokoro-onnx not installed (pip install --user kokoro-onnx)"
        try:
            import sounddevice  # noqa: F401
        except (ImportError, OSError):
            return "sounddevice not installed (pip install --user sounddevice)"
        if not MODEL_FILE.exists() or not VOICES_FILE.exists():
            return f"voice model missing in {MODEL_DIR}"
        return None

    def load(self) -> bool:
        """Load the model. Slow on first call; safe to call from a worker."""
        problem = self._missing()
        if problem:
            self.status = problem
            return False
        with self._load_lock:
            if self._kokoro is None:
                from kokoro_onnx import Kokoro

                self._kokoro = Kokoro(str(MODEL_FILE), str(VOICES_FILE))
        self.status = f"ready ({self.voice_name})"
        return True

    def list_voices(self) -> list[str]:
        if not self.load():
            return []
        try:
            return sorted(self._kokoro.get_voices())
        except Exception:
            return []

    def set_voice(self, name: str) -> bool:
        voices = self.list_voices()
        matches = [v for v in voices if name.lower() in v.lower()]
        if not matches:
            return False
        self.voice_name = matches[0]
        self.status = f"ready ({self.voice_name})"
        return True

    # ── speaking ─────────────────────────────────────────────────

    def stop(self) -> None:
        """Stop the utterance being played right now."""
        self._stop.set()

    def mute(self) -> None:
        """Stop talking now and stay silent until unmuted.

        A plain stop() is not enough to keep her quiet: speak() clears the stop
        flag when it starts, so a reply that is still being generated would
        begin talking anyway. The mute survives until it is lifted.
        """
        self._muted = True
        self._stop.set()

    def unmute(self) -> None:
        self._muted = False
        # Playback has already exited by now, so clear the stop the mute set
        # rather than leaving the object in a halted state.
        self._stop.clear()

    @property
    def _halted(self) -> bool:
        return self._muted or self._stop.is_set()

    def speak(self, text: str) -> None:
        """Synthesise and play `text`. Blocking — run it in a worker thread."""
        if not self.enabled or self._muted:
            return
        chunks = split_sentences(text)
        if not chunks or not self.load():
            return

        import sounddevice as sd

        self._stop.clear()
        if self._muted:  # muted while we were loading
            return
        self._set_state(True)
        stream = None
        try:
            for chunk in chunks:
                if self._halted:
                    break
                samples, rate = self._kokoro.create(
                    chunk, voice=self.voice_name, speed=1.0, lang=LANG
                )
                samples = np.asarray(samples, dtype=np.float32)
                if samples.size == 0:
                    continue
                if stream is None:
                    stream = sd.OutputStream(
                        samplerate=rate, channels=1,
                        dtype="float32", blocksize=BLOCK,
                    )
                    stream.start()
                self._play(stream, samples, rate)
        except Exception as exc:
            self.status = f"speech failed: {exc}"
        finally:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
            self._set_state(False)

    def _play(self, stream, samples: np.ndarray, rate: int) -> None:
        for start in range(0, samples.size, BLOCK):
            if self._halted:
                return
            block = samples[start:start + BLOCK]
            self._emit_level(block, rate)
            if block.size < BLOCK:
                block = np.pad(block, (0, BLOCK - block.size))
            stream.write(block.reshape(-1, 1))

    def _emit_level(self, block: np.ndarray, rate: int) -> None:
        if self._on_level is None:
            return
        rms = float(np.sqrt(np.mean(block.astype(np.float64) ** 2)))
        level = float(np.clip(rms * 7.0, 0.0, 1.0))
        try:
            self._on_level(level, _spectrum(block, rate))
        except Exception:
            pass

    def _set_state(self, speaking: bool) -> None:
        if self._on_state is None:
            return
        try:
            self._on_state(speaking)
        except Exception:
            pass
