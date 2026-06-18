"""Feature Engine.

For each symbol maintains a SymbolBuffer and, on demand, computes the full
feature bundle across every configured rolling window plus a data-quality
snapshot. Pure/stateless w.r.t. scoring: it only describes the market.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..models import DataQuality, DigitFeatures, MovementFeatures, Tick
from .digit_features import DigitConfig, compute_digit_features
from .movement_features import MovementConfig, compute_movement_features
from .windows import SymbolBuffer


@dataclass
class FeatureBundle:
    symbol: str
    epoch: int
    digit: dict[int, DigitFeatures] = field(default_factory=dict)      # window -> features
    movement: dict[int, MovementFeatures] = field(default_factory=dict)
    data_quality: DataQuality = field(default_factory=DataQuality)

    def primary_digit(self, primary_window: int) -> DigitFeatures:
        return self.digit[primary_window]

    def primary_movement(self, primary_window: int) -> MovementFeatures:
        return self.movement[primary_window]


class FeatureEngine:
    def __init__(
        self,
        windows: list[int],
        digit_cfg: DigitConfig,
        movement_cfg: MovementConfig,
        staleness_warn_ms: float = 3000.0,
    ) -> None:
        self.windows = sorted(set(windows))
        self.digit_cfg = digit_cfg
        self.movement_cfg = movement_cfg
        self.staleness_warn_ms = staleness_warn_ms
        self._buffers: dict[str, SymbolBuffer] = {}
        self._last_latency_ms: dict[str, float] = {}

    def buffer(self, symbol: str) -> SymbolBuffer:
        if symbol not in self._buffers:
            self._buffers[symbol] = SymbolBuffer(symbol, self.windows)
        return self._buffers[symbol]

    def seed(self, symbol: str, ticks: list[Tick]) -> None:
        self.buffer(symbol).seed(ticks)

    def ingest(self, tick: Tick) -> None:
        self.buffer(tick.symbol).add(tick)

    def set_latency(self, symbol: str, latency_ms: float) -> None:
        self._last_latency_ms[symbol] = latency_ms

    def ready(self, symbol: str, min_count: int) -> bool:
        return len(self.buffer(symbol)) >= min_count

    def compute(self, symbol: str, now_monotonic: float | None = None) -> FeatureBundle:
        buf = self.buffer(symbol)
        now = now_monotonic if now_monotonic is not None else time.monotonic()
        bundle = FeatureBundle(symbol=symbol, epoch=buf.last_epoch)

        for w in self.windows:
            digits = buf.digits(w)
            bundle.digit[w] = compute_digit_features(digits, w, self.digit_cfg)
            deltas_pips = buf.deltas_in_pips(w)
            quotes_pips = buf.quotes_in_pips(w)
            bundle.movement[w] = compute_movement_features(
                deltas_pips, quotes_pips, w, self.movement_cfg
            )

        bundle.data_quality = self._data_quality(symbol, buf, now)
        return bundle

    def _data_quality(self, symbol: str, buf: SymbolBuffer, now: float) -> DataQuality:
        age_ms = (now - buf.last_recv_ts) * 1000.0 if buf.last_recv_ts else 0.0
        latency = self._last_latency_ms.get(symbol, 0.0)
        fresh = age_ms <= self.staleness_warn_ms

        # Quality score: penalise staleness, latency and feed gaps.
        score = 100.0
        if age_ms > self.staleness_warn_ms:
            score -= min(50.0, (age_ms - self.staleness_warn_ms) / 100.0)
        score -= min(25.0, latency / 200.0)
        score -= min(25.0, buf.gap_count * 2.0)
        score = max(0.0, score)

        return DataQuality(
            fresh=fresh,
            last_tick_age_ms=age_ms,
            latency_ms=latency,
            gap_count=buf.gap_count,
            quality_score=score,
        )
