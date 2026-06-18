"""Trade Health Meter.

A 0..100 score describing the health of an *open* (or candidate) position,
comparing live metrics to the entry baseline. It is intentionally distinct from
the Deterioration Detector: deterioration measures *change dynamics* (CUSUM /
z-score / bursts), whereas Trade Health is a steadier, baseline-relative
"is this position still good?" gauge driven by the configured weights.

Labels: HEALTHY / WATCH_CLOSELY / DETERIORATING / CRITICAL / EXIT_IF_POSSIBLE.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import mathx
from ..constants import HealthLabel
from ..features.feature_engine import FeatureBundle
from ..models import EntryBaseline, MarketScore, StabilityFeatures, TradeHealth


@dataclass
class TradeHealthConfig:
    weights: dict[str, float]
    labels: dict[str, float]

    @classmethod
    def from_dict(cls, d: dict) -> "TradeHealthConfig":
        default_w = {
            "mqs_delta": 0.30, "stability_delta": 0.20, "volatility_delta": 0.15,
            "jump_delta": 0.15, "trend_delta": 0.05, "danger_increase": 0.05,
            "data_quality": 0.05, "time_in_trade": 0.05,
        }
        w = {**default_w, **(d.get("weights") or {})}
        total = sum(max(0.0, v) for v in w.values()) or 1.0
        w = {k: max(0.0, v) / total for k, v in w.items()}
        labels = {
            "healthy": 80.0, "watch_closely": 65.0,
            "deteriorating": 45.0, "critical": 25.0,
        }
        labels.update(d.get("labels") or {})
        return cls(weights=w, labels=labels)


class TradeHealthMeter:
    def __init__(self, cfg: TradeHealthConfig, expected_trade_ticks: int = 120) -> None:
        self.cfg = cfg
        self.expected_trade_ticks = expected_trade_ticks

    def evaluate(
        self,
        baseline: EntryBaseline,
        score: MarketScore,
        stability: StabilityFeatures,
        bundle: FeatureBundle,
        ticks_in_trade: int = 0,
    ) -> TradeHealth:
        m = bundle.movement[stability.window]

        # Each component is a 0..1 "health" value (1 = as good as / better than entry).
        mqs_delta = mathx.clamp(score.mqs / max(baseline.mqs, 1e-9))
        stability_delta = mathx.clamp(stability.stability_score / max(baseline.stability, 1e-9))
        # Volatility: lower-or-equal vs baseline is healthy; expansion hurts.
        vol_ratio = m.realized_vol / max(baseline.volatility, 1e-9)
        volatility_delta = mathx.clamp(1.0 - max(0.0, vol_ratio - 1.0) / 2.0)
        # Jump risk increase hurts.
        jump_delta = mathx.clamp(1.0 - max(0.0, stability.jump_burst_prob - baseline.jump_risk) / 0.4)
        # Trend contradiction hurts.
        if abs(baseline.trend_slope) > 1e-9 and baseline.trend_slope * m.trend_slope < 0:
            trend_delta = mathx.clamp(1.0 - abs(m.trend_slope) / (abs(baseline.trend_slope) + 1e-9))
        else:
            trend_delta = 1.0
        danger_increase = mathx.clamp(1.0 - max(0.0, score.danger_pct - baseline.danger_rate) / 0.2)
        data_quality = mathx.clamp(bundle.data_quality.quality_score / 100.0)
        # Time-in-trade: mild decay as the position approaches expected horizon
        # (longer exposure => more cumulative knockout probability).
        time_in_trade = mathx.clamp(1.0 - ticks_in_trade / max(self.expected_trade_ticks, 1))

        comps = {
            "mqs_delta": mqs_delta,
            "stability_delta": stability_delta,
            "volatility_delta": volatility_delta,
            "jump_delta": jump_delta,
            "trend_delta": trend_delta,
            "danger_increase": danger_increase,
            "data_quality": data_quality,
            "time_in_trade": time_in_trade,
        }
        health = 100.0 * sum(self.cfg.weights[k] * v for k, v in comps.items())
        label = self._label(health)
        return TradeHealth(
            symbol=score.symbol,
            epoch=score.epoch,
            health_score=round(health, 2),
            label=label,
            components={k: round(v, 3) for k, v in comps.items()},
        )

    def _label(self, health: float) -> HealthLabel:
        lab = self.cfg.labels
        if health >= lab["healthy"]:
            return HealthLabel.HEALTHY
        if health >= lab["watch_closely"]:
            return HealthLabel.WATCH_CLOSELY
        if health >= lab["deteriorating"]:
            return HealthLabel.DETERIORATING
        if health >= lab["critical"]:
            return HealthLabel.CRITICAL
        return HealthLabel.EXIT_IF_POSSIBLE
