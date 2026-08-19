"""Shared subpixel canvas for Kaya's visualisers.

Resolution comes from packing subpixels into each character cell. Sextants
(U+1FB00, drawn natively by WezTerm) give a 2x3 grid per cell — three times the
pixels of a half block, and twice the horizontal resolution, which is what
mostly determines how blocky a drawing looks. Each cell carries two colours, so
every cell is fitted with a foreground/background pair.

Subclasses implement `field()` and get bloom, tone mapping, glyph packing and
the audio/state plumbing for free.
"""

from __future__ import annotations

import os

import numpy as np
from rich.segment import Segment
from rich.style import Style
from textual.strip import Strip
from textual.widget import Widget

MODE = os.environ.get("KAYA_VIZ_MODE", "sextant").lower()
SUB_X, SUB_Y = (2, 3) if MODE == "sextant" else (1, 2)

# Terminal cells are taller than they are wide, so subpixels are too. Anything
# that needs to look round has to correct for it.
CELL_ASPECT = float(os.environ.get("KAYA_CELL_ASPECT", "1.85"))
ASPECT = CELL_ASPECT * SUB_X / SUB_Y  # subpixel height / width

NUM_BANDS = 16
FPS = 30
LEVELS = 48

# Electric cyan ramp: deep void -> plasma -> white-hot core.
_STOPS = (
    (0.00, (8, 13, 20)),
    (0.16, (14, 48, 96)),
    (0.34, (18, 104, 178)),
    (0.52, (36, 166, 232)),
    (0.68, (96, 220, 255)),
    (0.82, (164, 242, 255)),
    (0.93, (216, 251, 255)),
    (1.00, (255, 255, 255)),
)


def make_palette(stops: tuple) -> list[str]:
    """A LEVELS-long list of rgb() strings interpolated through colour stops."""
    xs = np.linspace(0.0, 1.0, LEVELS)
    pos = [s[0] for s in stops]
    chan = [np.interp(xs, pos, [s[1][c] for s in stops]) for c in range(3)]
    return [
        f"rgb({int(chan[0][i])},{int(chan[1][i])},{int(chan[2][i])})"
        for i in range(LEVELS)
    ]


PALETTE = make_palette(_STOPS)
VOID = PALETTE[0]


def _sextant_char(value: int) -> str:
    """Map a 6-bit subpixel mask to its Unicode glyph.

    Bits run left-to-right, top-to-bottom. The Legacy Computing block omits the
    three masks that already exist elsewhere: empty, left half and right half.
    """
    if value == 0:
        return " "
    if value == 63:
        return "█"
    if value == 21:
        return "▌"
    if value == 42:
        return "▐"
    index = value - 1
    if value > 21:
        index -= 1
    if value > 42:
        index -= 1
    return chr(0x1FB00 + index)


_SEXTANTS = [_sextant_char(v) for v in range(64)]
_BITS = np.array([1, 2, 4, 8, 16, 32], dtype=np.uint8)


def blur(a: np.ndarray) -> np.ndarray:
    """Separable 5-tap blur used for the bloom pass."""
    p = np.pad(a, ((2, 2), (0, 0)))
    v = (p[:-4] + 4.0 * p[1:-3] + 6.0 * p[2:-2] + 4.0 * p[3:-1] + p[4:]) / 16.0
    p = np.pad(v, ((0, 0), (2, 2)))
    return (
        p[:, :-4] + 4.0 * p[:, 1:-3] + 6.0 * p[:, 2:-2] + 4.0 * p[:, 3:-1] + p[:, 4:]
    ) / 16.0


class Visualizer(Widget):
    """State and audio plumbing shared by all of Kaya's visualisers."""

    can_focus = False

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.time = 0.0
        self._state = "idle"

        self.level = 0.0
        self._target_level = 0.0
        self.bands = np.zeros(NUM_BANDS)
        self._target_bands = np.zeros(NUM_BANDS)
        self._ticks = 0

    # ── public API ───────────────────────────────────────────────

    @property
    def state(self) -> str:
        return self._state

    def set_state(self, state: str) -> None:
        """One of: idle, thinking, speaking, listening."""
        self._state = state
        # speaking and listening are both driven by a live audio feed.
        if state not in ("speaking", "listening"):
            self._target_level = 0.0
            self._target_bands[:] = 0.0

    def push_audio(self, level: float, bands: np.ndarray | None = None) -> None:
        """Feed one block of playing audio. Safe to call from the audio thread."""
        self._target_level = float(np.clip(level, 0.0, 1.0))
        if bands is not None and bands.size == NUM_BANDS:
            self._target_bands = np.clip(bands, 0.0, 1.0)

    # ── subclass hooks ───────────────────────────────────────────

    def render_frame(self) -> None:
        """Recompute whatever render_line() needs for the current instant."""
        raise NotImplementedError

    def advance(self, dt: float) -> None:
        """Step any subclass-owned animation state."""

    # ── animation ────────────────────────────────────────────────

    def on_mount(self) -> None:
        self.set_interval(1.0 / FPS, self._tick)

    def _tick(self) -> None:
        # Idling costs nothing to look at, so halve the frame rate there.
        self._ticks += 1
        if self._state == "idle" and self._ticks % 2:
            return

        dt = (2.0 if self._state == "idle" else 1.0) / FPS
        self.time += dt

        # Fast attack so it snaps to speech, slower decay so it glides back.
        rate = 1.0 - (0.45 if self._target_level > self.level else 0.88) ** (dt * FPS)
        self.level += (self._target_level - self.level) * rate

        rates = np.where(self._target_bands > self.bands, 0.55, 0.15)
        self.bands = self.bands + (self._target_bands - self.bands) * rates

        self.advance(dt)
        self.render_frame()
        self.refresh()


class GlyphCanvas(Visualizer):
    """A subpixel drawing surface driven by playback audio."""

    BLOOM = 0.55  # glow strength
    GAIN = 2.6    # tone-mapping exposure

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._frame: np.ndarray | None = None
        self._style_cache: dict[tuple[int, int], Style] = {}

    def field(self, h: int, w: int) -> np.ndarray:
        """Return a non-negative (h, w) energy field. Bloom and tone mapping follow."""
        raise NotImplementedError

    def render_frame(self) -> None:
        self._frame = self._render_frame()

    def _render_frame(self) -> np.ndarray | None:
        width, height = self.size.width, self.size.height
        if width < 4 or height < 2:
            return None

        energy = self.field(height * SUB_Y, width * SUB_X)
        energy = energy + self.BLOOM * blur(blur(energy))

        gain = self.GAIN * (1.0 + 0.8 * self.level)
        tone = 1.0 - np.exp(-np.maximum(energy, 0.0) * gain)
        return np.clip(tone * (LEVELS - 1), 0, LEVELS - 1).astype(np.uint8)

    # ── glyph packing ────────────────────────────────────────────

    def _style_for(self, fg: int, bg: int) -> Style:
        key = (fg, bg)
        style = self._style_cache.get(key)
        if style is None:
            style = Style(color=PALETTE[fg], bgcolor=PALETTE[bg])
            self._style_cache[key] = style
        return style

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        frame = self._frame
        if (
            frame is None
            or frame.shape[1] != width * SUB_X
            or (y + 1) * SUB_Y > frame.shape[0]
        ):
            return Strip.blank(width, Style(bgcolor=VOID))

        cell = frame[y * SUB_Y:(y + 1) * SUB_Y]            # (SUB_Y, width*SUB_X)
        cell = cell.reshape(SUB_Y, width, SUB_X)           # (SUB_Y, width, SUB_X)
        cell = cell.transpose(1, 0, 2).reshape(width, -1)  # (width, SUB_Y*SUB_X)

        hi = cell.max(axis=1)
        lo = cell.min(axis=1)
        mask = cell > ((hi + lo) * 0.5)[:, None]
        values = (mask * _BITS[: cell.shape[1]]).sum(axis=1)

        chars = _SEXTANTS if SUB_X == 2 else None
        vals, his, los = values.tolist(), hi.tolist(), lo.tolist()

        segments: list[Segment] = []
        run_start = 0
        run_key = (vals[0], his[0], los[0])

        def flush(end: int) -> None:
            count = end - run_start
            if count <= 0:
                return
            value, fg, bg = run_key
            if chars is None:
                # Half blocks: upper pixel is the foreground, lower the background.
                segments.append(
                    Segment("▀" * count, self._style_for(fg if value & 1 else bg,
                                                         fg if value & 2 else bg))
                )
            elif value == 0:
                segments.append(Segment(" " * count, self._style_for(bg, bg)))
            else:
                segments.append(Segment(chars[value] * count, self._style_for(fg, bg)))

        for i in range(1, width):
            key = (vals[i], his[i], los[i])
            if key != run_key:
                flush(i)
                run_start = i
                run_key = key
        flush(width)

        return Strip(segments, width)
