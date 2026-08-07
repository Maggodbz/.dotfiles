"""A mirrored sound wave built from eighth-block bars.

Character cells can show a vertical bar at eight sub-heights (▁▂▃▄▅▆▇█), so a
column of them renders as a clean rectangle with no stair-stepping — unlike
freeform curves, this cannot look pixelated. Bars grow symmetrically from a
centre line: upward with lower-block glyphs, downward by drawing the same
glyphs with foreground and background swapped so the filled part hangs from
the top of the cell.

Idle shows a thin rippling line, thinking sweeps a pulse from side to side,
and speech maps the spectrum across the width (low frequencies in the centre,
mirrored outward) so the wave dances with the voice.
"""

from __future__ import annotations

import numpy as np
from rich.segment import Segment
from rich.style import Style
from textual.strip import Strip

from .render import LEVELS, NUM_BANDS, PALETTE, VOID, Visualizer, make_palette

FILL = 0.34       # fraction of the half-height the loudest bar may reach
TIP_FADE = 0.55   # how much bars darken towards their tips
HAIRLINE = "#3D5468"
_LOWER = " ▁▂▃▄▅▆▇█"

# Listening is *your* voice, so it gets a warm amber ramp to set it apart from
# Kaya's cyan when she speaks.
_AMBER_STOPS = (
    (0.00, (8, 13, 20)),
    (0.20, (60, 40, 16)),
    (0.45, (140, 88, 30)),
    (0.68, (214, 150, 70)),
    (0.86, (240, 200, 120)),
    (1.00, (255, 240, 210)),
)
AMBER_PALETTE = make_palette(_AMBER_STOPS)


class Wave(Visualizer):
    """Kaya's voice as a symmetric, grid-aligned waveform."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._eighths: np.ndarray | None = None  # bar half-extent per column
        self._levels: np.ndarray | None = None   # palette level per column
        self._extent = 1
        self._style_cache: dict[tuple[str, int], Style] = {}
        # Stable per-column variation: without it neighbouring bars get almost
        # the same height and the wave reads as solid lumps instead of bars.
        self._jitter = np.random.default_rng(3).uniform(0.4, 1.0, 4096)

    # ── per-frame column heights ─────────────────────────────────

    def render_frame(self) -> None:
        w, h = self.size.width, self.size.height
        if w < 8 or h < 5:
            self._eighths = None
            return

        t = self.time
        x = np.arange(w)
        cx = (w - 1) / 2.0
        d = np.abs(x - cx) / max(cx, 1.0)  # 0 centre .. 1 edge

        # At rest the wave is a near-hairline with a faint travelling swell.
        ripple = 0.5 + 0.5 * np.sin(x * 0.42 - t * 2.6)
        breathe = 0.72 + 0.28 * np.sin(t * 0.9)
        v = 0.012 + 0.03 * ripple * breathe

        jitter = self._jitter[:w]
        if self._state == "thinking":
            x0 = cx * (1.0 + 0.72 * np.sin(t * 2.1))
            pulse = np.exp(-(((x - x0) / (w * 0.055)) ** 2))
            v = v + 0.55 * pulse * jitter
        elif self.level > 0.01:
            env = np.interp(d * (NUM_BANDS - 1), np.arange(NUM_BANDS), self.bands)
            shimmer = 0.82 + 0.18 * np.sin(x * 0.31 + t * 6.5)
            v = np.maximum(v, env * self.level * shimmer * jitter)

        # Edges taper so the wave has a shape instead of hitting the border.
        v = np.clip(v, 0.0, 1.0) * (1.0 - 0.55 * d**3)

        self._extent = max(int((h // 2) * 8 * FILL), 8)
        self._eighths = np.maximum((v * self._extent).astype(np.int32), 1)
        self._levels = (np.sqrt(v) * (LEVELS - 1)).astype(np.int32)

    # ── drawing ──────────────────────────────────────────────────

    def _hairline(self) -> Style:
        style = self._style_cache.get(("hair", 0))
        if style is None:
            style = Style(color=HAIRLINE, bgcolor=VOID)
            self._style_cache[("hair", 0)] = style
        return style

    def _style(self, bg_is_bar: bool, level: int) -> Style:
        amber = self._state == "listening"
        key = (amber, bg_is_bar, level)
        style = self._style_cache.get(key)
        if style is None:
            bar = (AMBER_PALETTE if amber else PALETTE)[level]
            style = (
                Style(color=VOID, bgcolor=bar)
                if bg_is_bar
                else Style(color=bar, bgcolor=VOID)
            )
            self._style_cache[key] = style
        return style

    def render_line(self, y: int) -> Strip:
        w, h = self.size.width, self.size.height
        if self._eighths is None or self._eighths.size != w:
            return Strip.blank(w, Style(bgcolor=VOID))

        upper = y < h // 2
        centre_row = y in (h // 2 - 1, h // 2)
        # Eighths between the centre line and the near edge of this row's cell.
        d0 = ((h // 2 - 1 - y) if upper else (y - h // 2)) * 8
        part = np.clip(self._eighths - d0, 0, 8)

        # Bars fade towards their tips, brightest at the centre line.
        fade = 1.0 - TIP_FADE * np.clip(
            d0 / np.maximum(self._eighths, 1), 0.0, 1.0
        )
        lvl = (self._levels * fade).astype(np.int32)

        parts, lvls = part.tolist(), lvl.tolist()
        segments: list[Segment] = []
        run_start = 0
        run_key = (parts[0], lvls[0])

        def flush(end: int) -> None:
            count = end - run_start
            if count <= 0:
                return
            p, level = run_key
            if p == 0:
                segments.append(Segment(" " * count, self._style(False, 0)))
            elif p == 1 and centre_row:
                # The resting wave is a dotted hairline, not a block.
                if upper:
                    segments.append(Segment("╌" * count, self._hairline()))
                else:
                    segments.append(Segment(" " * count, self._style(False, 0)))
            elif p == 8:
                segments.append(Segment("█" * count, self._style(False, level)))
            elif upper:
                # Filled from the bottom of the cell.
                segments.append(
                    Segment(_LOWER[p] * count, self._style(False, level))
                )
            else:
                # Filled from the top: draw the complement with colours swapped.
                segments.append(
                    Segment(_LOWER[8 - p] * count, self._style(True, level))
                )

        for i in range(1, w):
            key = (parts[i], lvls[i])
            if key != run_key:
                flush(i)
                run_start = i
                run_key = key
        flush(w)

        return Strip(segments, w)
