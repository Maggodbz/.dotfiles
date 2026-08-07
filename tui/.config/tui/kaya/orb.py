"""Audio-reactive 3D sphere rendered with Unicode half-blocks.

Each character cell carries two vertically stacked pixels: the upper half block
takes the foreground colour, the cell background paints the lower half. That
doubles vertical resolution and makes the pixels roughly square, since a
terminal cell is about twice as tall as it is wide.
"""

from __future__ import annotations

import numpy as np
from rich.segment import Segment
from rich.style import Style
from textual.strip import Strip
from textual.widget import Widget

NUM_POINTS = 1600
NUM_BANDS = 16
FPS = 30
LEVELS = 24
SWELL = 0.26   # how far a loud band pushes the surface out
BREATH = 0.03  # idle "alive" pulse
FOCAL = 3.2    # perspective distance
FILL = 0.98    # fraction of the panel the fully swollen orb may occupy

# Nord ramp from background to full highlight, used as a depth/energy gradient.
_STOPS = (
    (0.00, (46, 52, 64)),
    (0.30, (59, 66, 82)),
    (0.50, (76, 86, 106)),
    (0.68, (94, 129, 172)),
    (0.82, (129, 161, 193)),
    (0.92, (136, 192, 208)),
    (1.00, (236, 239, 244)),
)


def _build_palette() -> list[tuple[int, int, int]]:
    xs = np.linspace(0.0, 1.0, LEVELS)
    stop_pos = [s[0] for s in _STOPS]
    channels = [
        np.interp(xs, stop_pos, [s[1][c] for s in _STOPS]) for c in range(3)
    ]
    return [
        (int(channels[0][i]), int(channels[1][i]), int(channels[2][i]))
        for i in range(LEVELS)
    ]


_PALETTE = _build_palette()


def _sphere_points() -> tuple[np.ndarray, np.ndarray]:
    """Fibonacci lattice: evenly distributed points on the unit sphere."""
    idx = np.arange(NUM_POINTS) + 0.5
    polar = np.arccos(1.0 - 2.0 * idx / NUM_POINTS)
    azimuth = np.pi * (1.0 + 5.0**0.5) * idx
    points = np.stack(
        [
            np.sin(polar) * np.cos(azimuth),
            np.cos(polar),
            np.sin(polar) * np.sin(azimuth),
        ],
        axis=1,
    )
    # Latitude picks the frequency band, so bass swells the bottom of the orb.
    bands = np.clip((polar / np.pi * NUM_BANDS).astype(int), 0, NUM_BANDS - 1)
    return points, bands


class Orb(Widget):
    """Kaya's face: a rotating sphere that reacts to speech."""

    can_focus = False

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._points, self._bands_of_point = _sphere_points()
        self._angle = 0.0
        self._time = 0.0
        self._state = "idle"

        self._level = 0.0
        self._target_level = 0.0
        self._bands = np.zeros(NUM_BANDS)
        self._target_bands = np.zeros(NUM_BANDS)

        self._frame: np.ndarray | None = None
        self._style_cache: dict[tuple[int, int], Style] = {}

    # ── public API ───────────────────────────────────────────────

    @property
    def state(self) -> str:
        return self._state

    def set_state(self, state: str) -> None:
        """One of: idle, thinking, speaking."""
        self._state = state
        if state != "speaking":
            self._target_level = 0.0
            self._target_bands[:] = 0.0

    def push_audio(self, level: float, bands: np.ndarray | None = None) -> None:
        """Feed one block of playing audio. Safe to call from the audio thread."""
        self._target_level = float(np.clip(level, 0.0, 1.0))
        if bands is not None and bands.size == NUM_BANDS:
            self._target_bands = np.clip(bands, 0.0, 1.0)

    # ── animation ────────────────────────────────────────────────

    def on_mount(self) -> None:
        self.set_interval(1.0 / FPS, self._tick)

    def _tick(self) -> None:
        dt = 1.0 / FPS
        self._time += dt

        spin = {"idle": 0.35, "thinking": 1.1, "speaking": 0.6}.get(self._state, 0.35)
        self._angle += spin * dt

        # Fast attack so the orb snaps to speech, slower decay so it glides back.
        for attr, target in (("_level", self._target_level),):
            current = getattr(self, attr)
            rate = 0.55 if target > current else 0.12
            setattr(self, attr, current + (target - current) * rate)

        rising = self._target_bands > self._bands
        rate = np.where(rising, 0.55, 0.15)
        self._bands = self._bands + (self._target_bands - self._bands) * rate

        self._frame = self._render_frame()
        self.refresh()

    def _render_frame(self) -> np.ndarray | None:
        width = self.size.width
        height = self.size.height
        if width < 4 or height < 2:
            return None

        px_h = height * 2
        buf = np.zeros((px_h, width), dtype=np.float32)

        # Rotate around Y, then tilt slightly around X for a 3/4 view.
        ca, sa = np.cos(self._angle), np.sin(self._angle)
        x = self._points[:, 0] * ca + self._points[:, 2] * sa
        z = -self._points[:, 0] * sa + self._points[:, 2] * ca
        y = self._points[:, 1]

        tilt = 0.32
        ct, st = np.cos(tilt), np.sin(tilt)
        y, z = y * ct - z * st, y * st + z * ct

        breath = BREATH * np.sin(self._time * 1.6)
        if self._state == "thinking":
            breath += BREATH * 1.3 * np.sin(self._time * 5.0)
        radius = 1.0 + breath + SWELL * self._bands[self._bands_of_point] * self._level

        # Perspective projection. A sphere's silhouette is magnified by
        # f/sqrt(f^2 - r^2), so the span reserves headroom for that on top of a
        # fully swollen radius; otherwise loud passages clip on the border.
        focal = FOCAL
        depth = z * radius
        scale = focal / (focal + depth)

        r_max = 1.0 + SWELL + BREATH * 2.3
        magnify = focal / np.sqrt(max(focal * focal - r_max * r_max, 1e-6))
        span = min((width - 1) * 0.5, (px_h - 1) * 0.5) * FILL / (r_max * magnify)

        cx = (width - 1) * 0.5
        cy = (px_h - 1) * 0.5
        sx = cx + x * radius * scale * span
        sy = cy + y * radius * scale * span

        near = 1.0 - (depth + 1.0) * 0.5
        intensity = 0.18 + 0.82 * np.clip(near, 0.0, 1.0) ** 1.6
        intensity = intensity * (0.75 + 0.25 * self._level)

        ix = np.rint(sx).astype(int)
        iy = np.rint(sy).astype(int)
        keep = (ix >= 0) & (ix < width) & (iy >= 0) & (iy < px_h)
        np.maximum.at(buf, (iy[keep], ix[keep]), intensity[keep])

        return np.clip(buf * (LEVELS - 1), 0, LEVELS - 1).astype(np.uint8)

    # ── rendering ────────────────────────────────────────────────

    def _style_for(self, top: int, bottom: int) -> Style:
        key = (top, bottom)
        style = self._style_cache.get(key)
        if style is None:
            style = Style(
                color=f"rgb({_PALETTE[top][0]},{_PALETTE[top][1]},{_PALETTE[top][2]})",
                bgcolor=(
                    f"rgb({_PALETTE[bottom][0]},"
                    f"{_PALETTE[bottom][1]},{_PALETTE[bottom][2]})"
                ),
            )
            self._style_cache[key] = style
        return style

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        frame = self._frame
        if frame is None or frame.shape[1] != width or y * 2 + 1 >= frame.shape[0]:
            return Strip.blank(width, Style())

        top_row = frame[y * 2]
        bottom_row = frame[y * 2 + 1]

        segments: list[Segment] = []
        run_start = 0
        run_key = (int(top_row[0]), int(bottom_row[0]))

        def flush(end: int) -> None:
            count = end - run_start
            if count <= 0:
                return
            segments.append(Segment("▀" * count, self._style_for(*run_key)))

        for i in range(1, width):
            key = (int(top_row[i]), int(bottom_row[i]))
            if key != run_key:
                flush(i)
                run_start = i
                run_key = key
        flush(width)

        return Strip(segments, width)
