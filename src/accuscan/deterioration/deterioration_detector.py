"""Deterioration Detector.

When a symbol becomes READY (or a trade is entered) an *entry baseline* of the
key metrics is frozen. Every subsequent tick the live metrics are compared to
that baseline using a panel of online detectors, fused into a single 0..100
deterioration score with a health label, an alert level and a recommended
action.

This is the module that catches "sudden expectational changes that can create a
negative outcome" AFTER entry — the user's core safety requirement.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import mathx
from ..constants import AlertLevel, HealthLabel
from ..features.feature_engine import FeatureBundle
from ..models import DeteriorationResult, EntryBaseline, MarketScore, StabilityFeatures
from .detectors import CUSUM, EWMA, BurstDetector, RollingZScore


@dataclass
class DeteriorationConfig:
    cusum_k: float = 0.5
    cusum_h: float = 5.0
    ewma_lambda: float = 0.06
    zscore_window: int = 50
    zscore_warn: float = 2.5
    zscore_crit: float = 3.5
    score_drop_warn: float = 10.0
    score_drop_crit: float = 20.0
    latency_warn_ms: float = 1500.0
    latency_crit_ms: float = 4000.0
    staleness_warn_ms: float = 3000.0

    @classmethod
    def from_dict(cls, d: dict) -> "DeteriorationConfig":
        return cls(
            cusum_k=float(d.get("cusum_k", 0.5)),
            cusum_h=float(d.get("cusum_h", 5.0)),
            ewma_lambda=float(d.get("ewma_lambda", 0.06)),
            zscore_window=int(d.get("zscore_window", 50)),
            zscore_warn=float(d.get("zscore_warn", 2.5)),
            zscore_crit=float(d.get("zscore_crit", 3.5)),
            score_drop_warn=float(d.get("score_drop_warn", 10.0)),
            score_drop_crit=float(d.get("score_drop_crit", 20.0)),
            latency_warn_ms=float(d.get("latency_warn_ms", 1500.0)),
            latency_crit_ms=float(d.get("latency_crit_ms", 4000.0)),
            staleness_warn_ms=float(d.get("staleness_warn_ms", 3000.0)),
        )


class _SymbolMonitor:
    def __init__(self, cfg: DeteriorationConfig) -> None:
        self.cusum = CUSUM(k=cfg.cusum_k, h=cfg.cusum_h)
        self.ewma = EWMA(lam=cfg.ewma_lambda)
        self.zvol = RollingZScore(window=cfg.zscore_window)
        self.jump_burst = BurstDetector(window=25, threshold=0.0)


class DeteriorationDetector:
    def __init__(self, cfg: DeteriorationConfig) -> None:
        self.cfg = cfg
        self._baselines: dict[str, EntryBaseline] = {}
        self._monitors: dict[str, _SymbolMonitor] = {}

    # --- baseline lifecycle -------------------------------------------------
    def set_baseline(
        self,
        score: MarketScore,
        stability: StabilityFeatures,
        bundle: FeatureBundle,
    ) -> EntryBaseline:
        m = bundle.movement[stability.window]
        baseline = EntryBaseline(
            symbol=score.symbol,
            epoch=score.epoch,
            mqs=score.mqs,
            stability=stability.stability_score,
            volatility=max(m.realized_vol, 1e-9),
            jump_risk=stability.jump_burst_prob,
            trend_slope=m.trend_slope,
            danger_rate=score.danger_pct,
            movement_risk=score.movement_risk_score,
            rolling_range=m.rolling_range,
            data_quality=bundle.data_quality.quality_score,
        )
        self._baselines[score.symbol] = baseline
        self._monitors[score.symbol] = _SymbolMonitor(self.cfg)
        return baseline

    def has_baseline(self, symbol: str) -> bool:
        return symbol in self._baselines

    def baseline(self, symbol: str) -> EntryBaseline | None:
        return self._baselines.get(symbol)

    def clear(self, symbol: str) -> None:
        self._baselines.pop(symbol, None)
        self._monitors.pop(symbol, None)

    # --- live update --------------------------------------------------------
    def update(
        self,
        score: MarketScore,
        stability: StabilityFeatures,
        bundle: FeatureBundle,
    ) -> DeteriorationResult:
        symbol = score.symbol
        base = self._baselines.get(symbol)
        if base is None:
            # No baseline -> nothing to deteriorate from; report neutral health.
            return DeteriorationResult(
                symbol=symbol, epoch=score.epoch, deterioration_score=0.0,
                health_label=HealthLabel.HEALTHY, alert_level=AlertLevel.INFO,
                recommended_action="monitor", reasons=["no_baseline"],
            )

        mon = self._monitors[symbol]
        m = bundle.movement[stability.window]
        dq = bundle.data_quality
        reasons: list[str] = []

        # 1. MQS score drop from entry.
        score_drop = base.mqs - score.mqs

        # 2. Volatility expansion vs baseline (standardised in baseline units).
        vol_dev = (m.realized_vol - base.volatility) / base.volatility
        cusum_val = mon.cusum.update(vol_dev)
        mon.ewma.update(m.realized_vol)
        zscore = mon.zvol.update(m.realized_vol)
        vol_ratio = m.realized_vol / base.volatility

        # 3. Jump-risk increase + burst.
        jump_increase = stability.jump_burst_prob - base.jump_risk
        burst_count = mon.jump_burst.update(float(m.jump_count))

        # 4. Trend contradiction (only meaningful if baseline had a clear trend).
        trend_contra = 0.0
        if abs(base.trend_slope) > 1e-9 and (base.trend_slope * m.trend_slope) < 0:
            trend_contra = mathx.clamp(abs(m.trend_slope) / (abs(base.trend_slope) + 1e-9))

        # 5. Danger-digit rate increase.
        danger_increase = score.danger_pct - base.danger_rate

        # 6. Latency / staleness.
        latency = dq.latency_ms
        stale = dq.last_tick_age_ms

        # --- component scores (each 0..1) ----------------------------------
        c_score_drop = mathx.clamp(score_drop / self.cfg.score_drop_crit)
        c_vol = mathx.clamp((vol_ratio - 1.0) / 2.0)          # +200% vol => 1.0
        c_cusum = mathx.clamp(cusum_val / self.cfg.cusum_h)
        c_z = mathx.clamp((abs(zscore) - self.cfg.zscore_warn) /
                          max(self.cfg.zscore_crit - self.cfg.zscore_warn, 1e-9))
        c_jump = mathx.clamp(jump_increase / 0.4) if jump_increase > 0 else 0.0
        c_burst = mathx.clamp(burst_count / 5.0)
        c_trend = trend_contra
        c_danger = mathx.clamp(danger_increase / 0.2) if danger_increase > 0 else 0.0
        c_latency = mathx.clamp(latency / self.cfg.latency_crit_ms)
        c_stale = mathx.clamp(stale / (self.cfg.staleness_warn_ms * 2))

        # weighted fusion -> 0..100
        det = 100.0 * mathx.clamp(
            0.24 * c_score_drop
            + 0.18 * c_vol
            + 0.12 * c_cusum
            + 0.10 * c_z
            + 0.12 * c_jump
            + 0.06 * c_burst
            + 0.06 * c_trend
            + 0.04 * c_danger
            + 0.04 * c_latency
            + 0.04 * c_stale
        )

        # reasons
        if score_drop >= self.cfg.score_drop_warn:
            reasons.append("score_drop")
        if vol_ratio >= 1.5:
            reasons.append("volatility_expansion")
        if mon.cusum.triggered:
            reasons.append("cusum_shift")
        if abs(zscore) >= self.cfg.zscore_warn:
            reasons.append("vol_zscore")
        if jump_increase > 0.1 or burst_count >= 2:
            reasons.append("jump_burst")
        if trend_contra > 0.3:
            reasons.append("trend_reversal")
        if danger_increase > 0.1:
            reasons.append("danger_digit_increase")
        if latency >= self.cfg.latency_warn_ms:
            reasons.append("latency")
        if not dq.fresh or stale >= self.cfg.staleness_warn_ms:
            reasons.append("data_staleness")

        alert_level = self._alert_level(det, score_drop, zscore, mon, latency, dq)
        label = self._health_label(det)
        action = self._action(label)

        return DeteriorationResult(
            symbol=symbol,
            epoch=score.epoch,
            deterioration_score=round(det, 2),
            health_label=label,
            alert_level=alert_level,
            recommended_action=action,
            cusum=round(cusum_val, 3),
            zscore=round(zscore, 3),
            ewma_vol=round(mon.ewma.vol, 4),
            score_drop=round(score_drop, 2),
            reasons=reasons,
        )

    # --- mappers ------------------------------------------------------------
    def _alert_level(self, det, score_drop, zscore, mon, latency, dq) -> AlertLevel:
        if (
            det >= 70.0
            or score_drop >= self.cfg.score_drop_crit
            or mon.cusum.triggered
            or abs(zscore) >= self.cfg.zscore_crit
            or latency >= self.cfg.latency_crit_ms
            or not dq.fresh
        ):
            return AlertLevel.CRITICAL
        if (
            det >= 40.0
            or score_drop >= self.cfg.score_drop_warn
            or abs(zscore) >= self.cfg.zscore_warn
            or latency >= self.cfg.latency_warn_ms
        ):
            return AlertLevel.WARNING
        return AlertLevel.INFO

    @staticmethod
    def _health_label(det: float) -> HealthLabel:
        if det < 20:
            return HealthLabel.HEALTHY
        if det < 40:
            return HealthLabel.WATCH_CLOSELY
        if det < 60:
            return HealthLabel.DETERIORATING
        if det < 80:
            return HealthLabel.CRITICAL
        return HealthLabel.EXIT_IF_POSSIBLE

    @staticmethod
    def _action(label: HealthLabel) -> str:
        return {
            HealthLabel.HEALTHY: "hold",
            HealthLabel.WATCH_CLOSELY: "monitor_closely",
            HealthLabel.DETERIORATING: "tighten_take_profit_or_prepare_exit",
            HealthLabel.CRITICAL: "exit_soon",
            HealthLabel.EXIT_IF_POSSIBLE: "exit_now_if_possible",
        }[label]
