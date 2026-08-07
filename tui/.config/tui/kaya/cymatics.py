"""Chladni figures — sound made visible.

A circular plate clamped at its rim vibrates in modes

    phi(r, theta) = J_n(lambda_nm * r) * cos(n * theta + phase)

where lambda_nm is the m-th zero of the Bessel function J_n, which puts a nodal
circle exactly on the rim. Sand on a real plate collects where the surface is
still, so the figure is the nodal set of the summed displacement: the curve
u = 0.

Each audio band drives one mode. Modes are ordered by lambda, so low
frequencies excite coarse figures and high frequencies fine ones, exactly as a
real plate behaves.

Lines are drawn at the nodal set using the distance estimate |u| / |grad u|,
which is scale invariant and so gives a constant line width no matter how
loudly the plate is driven.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from .render import ASPECT, NUM_BANDS, GlyphCanvas

N_MODES = 16     # one per audio band
MAX_ORDER = 8    # highest angular order n
MAX_RADIAL = 6   # highest radial order m

FILL = 0.94      # fraction of the panel the plate spans
LINE_W = 0.8     # nodal line half-width, in subpixels
IDLE_AMP = 0.7   # how strongly modes ring when nothing is being said
DRIVE = 2.2      # how strongly audio bands excite their mode
SHARPNESS = 2.5  # >1 lets the loudest band's mode dominate the figure


@lru_cache(maxsize=1)
def _besselj_table(
    nmax: int, xmax: float, samples: int = 2048, quad: int = 384
) -> tuple[np.ndarray, np.ndarray]:
    """Tabulate J_0..J_nmax via J_n(x) = 1/pi * int_0^pi cos(n*t - x*sin t) dt.

    Avoids a scipy dependency; the integrand is smooth so the midpoint rule
    converges quickly.
    """
    x = np.linspace(0.0, xmax, samples)
    tau = (np.arange(quad) + 0.5) * (np.pi / quad)
    phase = x[:, None] * np.sin(tau)[None, :]
    table = np.empty((nmax + 1, samples))
    for n in range(nmax + 1):
        table[n] = np.cos(n * tau[None, :] - phase).mean(axis=1)
    return x, table


def _zeros(x: np.ndarray, y: np.ndarray, count: int) -> list[float]:
    """Positive roots of a tabulated function, refined by linear interpolation."""
    sign = np.signbit(y)
    crossings = np.nonzero(sign[1:] != sign[:-1])[0]
    roots: list[float] = []
    for i in crossings:
        if x[i] < 1.0:  # J_n(0) = 0 for n >= 1; not a mode
            continue
        y0, y1 = y[i], y[i + 1]
        roots.append(float(x[i] - y0 * (x[i + 1] - x[i]) / (y1 - y0)))
        if len(roots) == count:
            break
    return roots


class Cymatics(GlyphCanvas):
    """A vibrating plate whose nodal lines trace what Kaya is saying."""

    BLOOM = 0.35
    GAIN = 2.0

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._shape: tuple[int, int] | None = None
        self._planes: np.ndarray | None = None   # (P, h*w)
        self._cos_idx: np.ndarray | None = None
        self._sin_idx: np.ndarray | None = None
        self._edge: np.ndarray | None = None

        rng = np.random.default_rng(7)
        self._phase = rng.uniform(0.0, 2.0 * np.pi, N_MODES)
        self._drift = rng.uniform(0.04, 0.22, N_MODES) * rng.choice([-1, 1], N_MODES)
        self._idle_rate = rng.uniform(0.09, 0.31, N_MODES)
        self._idle_off = rng.uniform(0.0, 2.0 * np.pi, N_MODES)
        self._band_of = np.minimum(
            (np.arange(N_MODES) * NUM_BANDS) // N_MODES, NUM_BANDS - 1
        )

    # ── mode basis ───────────────────────────────────────────────

    def _prepare(self, h: int, w: int) -> None:
        xtab, table = _besselj_table(MAX_ORDER, 40.0)

        modes: list[tuple[float, int]] = []
        for n in range(MAX_ORDER + 1):
            for lam in _zeros(xtab, table[n], MAX_RADIAL):
                modes.append((lam, n))
        modes.sort()
        modes = modes[:N_MODES]

        cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
        ry = min(cy, cx / ASPECT) * FILL
        rx = ry * ASPECT

        yy = (np.arange(h)[:, None] - cy) / ry
        xx = (np.arange(w)[None, :] - cx) / rx
        r = np.hypot(xx, yy)
        theta = np.arctan2(yy, xx)

        # Full brightness out to the rim (itself a nodal circle), then one
        # subpixel of falloff so the edge is not stair-stepped.
        self._edge = np.clip((1.0 - r) * ry + 1.0, 0.0, 1.0).astype(np.float32)
        inside = r <= 1.0

        planes: list[np.ndarray] = []
        cos_idx = np.zeros(N_MODES, dtype=np.int32)
        sin_idx = np.full(N_MODES, -1, dtype=np.int32)

        for k, (lam, n) in enumerate(modes):
            radial = np.interp(lam * r, xtab, table[n]) * inside
            cos_idx[k] = len(planes)
            planes.append(radial * np.cos(n * theta))
            if n:
                sin_idx[k] = len(planes)
                planes.append(radial * np.sin(n * theta))

        stack = np.asarray(planes, dtype=np.float32)
        rms = np.sqrt((stack**2).mean(axis=(1, 2)))
        stack /= np.maximum(rms, 1e-9)[:, None, None]

        self._planes = stack.reshape(len(planes), h * w)
        self._cos_idx, self._sin_idx = cos_idx, sin_idx
        self._shape = (h, w)

    # ── per-frame field ──────────────────────────────────────────

    def advance(self, dt: float) -> None:
        speed = 2.4 if self.state == "thinking" else 1.0
        self._phase += self._drift * speed * dt

    def field(self, h: int, w: int) -> np.ndarray:
        if self._shape != (h, w):
            self._prepare(h, w)

        k = np.arange(N_MODES)
        idle = (
            IDLE_AMP
            * np.exp(-k / 7.0)
            * (0.55 + 0.45 * np.sin(self.time * self._idle_rate + self._idle_off))
        )

        # A real plate resonates in one mode at a time. Sharpening the band
        # energies keeps the figure legible and makes it snap between shapes as
        # the voice moves, instead of averaging into mush.
        drive = self.bands[self._band_of] ** SHARPNESS
        drive = drive / (drive.max() + 1e-6)

        amp = idle * (1.0 - 0.75 * self.level) + DRIVE * drive * self.level

        coef = np.zeros(self._planes.shape[0], dtype=np.float32)
        coef[self._cos_idx] = amp * np.cos(self._phase)
        angular = self._sin_idx >= 0
        coef[self._sin_idx[angular]] = (amp * np.sin(self._phase))[angular]

        u = (coef @ self._planes).reshape(h, w)

        # Distance to the nodal set, in subpixels. Scale invariant, so the lines
        # stay the same width however hard the plate is driven.
        gy, gx = np.gradient(u)
        grad = np.sqrt(gx * gx + gy * gy)
        grad += 0.02 * grad.mean() + 1e-9
        dist = np.abs(u) / grad

        return np.exp(-((dist / LINE_W) ** 2)) * self._edge
