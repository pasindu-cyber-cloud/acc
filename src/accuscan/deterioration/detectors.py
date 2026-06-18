"""Online change-detection primitives (stdlib only).

Each detector is a small stateful object updated one observation at a time, so
they run in O(1) per tick and are suitable for live monitoring after entry.

  - CUSUM:  detects a persistent shift in the mean of a standardised signal.
  - EWMA:   exponentially-weighted moving stats (level + volatility).
  - RollingZScore: deviation of the latest value from a rolling baseline.
  - BurstDetector: counts recent threshold exceedances within a short window.
"""

from __future__ import annotations

import math
from collections import deque

from .. import mathx


class CUSUM:
    """Two-sided CUSUM on a standardised signal (units = baseline sigmas).

    g_high accumulates upward shifts, g_low downward. A shift is flagged when
    either exceeds the decision threshold h. k is the allowance (slack).
    """

    def __init__(self, k: float = 0.5, h: float = 5.0, cap_mult: float = 2.0) -> None:
        self.k = k
        self.h = h
        # Cap the accumulators at cap_mult * h so a violent burst cannot
        # saturate the statistic. Without a cap, CUSUM can grow to hundreds and
        # then take hundreds of ticks (decaying by k each tick) to fall back
        # below h — emitting CRITICAL long after conditions have recovered.
        # Capping bounds the post-event recovery time to ~ (cap_mult-1)*h / k.
        self.cap = cap_mult * h
        self.g_high = 0.0
        self.g_low = 0.0

    def update(self, z: float) -> float:
        self.g_high = min(self.cap, max(0.0, self.g_high + z - self.k))
        self.g_low = min(self.cap, max(0.0, self.g_low - z - self.k))
        return self.value

    @property
    def value(self) -> float:
        return max(self.g_high, self.g_low)

    @property
    def triggered(self) -> bool:
        return self.value >= self.h

    def reset(self) -> None:
        self.g_high = 0.0
        self.g_low = 0.0


class EWMA:
    """Exponentially-weighted level and volatility estimator."""

    def __init__(self, lam: float = 0.06) -> None:
        self.lam = lam
        self.mean: float | None = None
        self.var: float = 0.0

    def update(self, x: float) -> None:
        if self.mean is None:
            self.mean = x
            self.var = 0.0
            return
        prev = self.mean
        self.mean = (1 - self.lam) * self.mean + self.lam * x
        # EWMA variance (RiskMetrics-style on deviations from previous mean).
        self.var = (1 - self.lam) * (self.var + self.lam * (x - prev) ** 2)

    @property
    def vol(self) -> float:
        return math.sqrt(max(self.var, 0.0))


class RollingZScore:
    """Z-score of the latest value against a rolling window baseline."""

    def __init__(self, window: int = 50) -> None:
        self.window = window
        self._buf: deque[float] = deque(maxlen=window)

    def update(self, x: float) -> float:
        self._buf.append(x)
        if len(self._buf) < 5:
            return 0.0
        data = list(self._buf)
        mu = mathx.mean(data)
        sd = mathx.std(data, ddof=1)
        if sd <= 1e-12:
            return 0.0
        return (x - mu) / sd


class BurstDetector:
    """Counts exceedances of `threshold` within the last `window` updates."""

    def __init__(self, window: int = 20, threshold: float = 0.0) -> None:
        self.window = window
        self.threshold = threshold
        self._buf: deque[int] = deque(maxlen=window)

    def update(self, x: float) -> int:
        self._buf.append(1 if x > self.threshold else 0)
        return sum(self._buf)

    @property
    def count(self) -> int:
        return sum(self._buf)
