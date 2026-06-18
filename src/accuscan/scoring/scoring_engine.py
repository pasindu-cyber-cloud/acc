"""Market Scoring Engine.

Turns a FeatureBundle (+ StabilityFeatures) into a 0..100 Market Quality Score
(MQS) via a configurable weighted blend of nine sub-scores, then derives a
READY / WATCH / HIGH_RISK status and tracks readiness persistence.

All sub-scores are expressed on a 0..100 "higher = better/safer" scale so the
weighted sum is itself a 0..100 quality score and the weights are interpretable.

See docs/SCORING.md for the formula reference.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import mathx
from ..config import RiskProfile
from ..constants import Status
from ..features.feature_engine import FeatureBundle
from ..models import MarketScore, StabilityFeatures, SubScores
from .weights import Weights


@dataclass
class ScoringConfig:
    primary_window: int = 100
    short_window: int = 25
    ready_threshold: float = 72.0
    watch_threshold: float = 55.0
    min_ready_persistence_ticks: int = 15

    @classmethod
    def from_dict(cls, scoring: dict, profile: RiskProfile) -> "ScoringConfig":
        th = scoring.get("thresholds", {})
        return cls(
            primary_window=int(scoring.get("primary_window", 100)),
            short_window=25,
            ready_threshold=float(profile.ready_threshold or th.get("ready", 72)),
            watch_threshold=float(th.get("watch", 55)),
            min_ready_persistence_ticks=int(
                scoring.get("min_ready_persistence_ticks", profile.min_ready_persistence_ticks)
            ),
        )


def _digit_cleanliness(danger_pct: float, expected: float, cluster: float,
                       bursts: int, entropy: float, entropy_floor: float) -> float:
    """0..100. Penalise danger digits ABOVE the uniform expectation. Clustering
    and bursts are only penalised when danger digits are also in excess, because
    at the expected rate some clustering/bursting occurs purely by chance and is
    not a genuine anomaly (the hard veto layer handles extreme clustering)."""
    excess = max(0.0, danger_pct - expected)
    # 0 at/below expectation, ramps to 1 once danger is ~15% above expectation.
    excess_factor = mathx.clamp(excess / 0.15)
    penalty = (
        1.6 * excess
        + 0.5 * cluster * excess_factor
        + 0.10 * min(bursts, 5) * excess_factor
    )
    if entropy < entropy_floor:
        penalty += 0.4 * (entropy_floor - entropy) / max(entropy_floor, 1e-9)
    return mathx.clamp(1.0 - penalty) * 100.0


def _movement_safety(m) -> float:
    """0..100 movement-risk SAFETY. For accumulators the band is per-tick, so
    safety is driven by the upper tail of |delta| relative to the typical move
    and by large-move frequency; choppiness within the band is only a minor
    factor (it does not by itself cause a knockout)."""
    large_freq = m.large_move_count / max(m.count, 1)
    excess_tail = max(0.0, m.tail_ratio - 3.8)
    tail_risk = mathx.clamp(excess_tail / 6.0)
    risk = (
        0.50 * tail_risk
        + 0.25 * m.jump_proxy
        + 0.15 * mathx.clamp(large_freq * 8.0)
        + 0.10 * m.chop_score
    )
    return mathx.clamp(1.0 - risk) * 100.0


def _jump_safety(stab: StabilityFeatures) -> float:
    return mathx.clamp(1.0 - stab.jump_burst_prob) * 100.0


def _trend_smoothness(stab: StabilityFeatures, m) -> float:
    return mathx.clamp(0.6 * stab.smoothness + 0.4 * (1.0 - m.chop_score)) * 100.0


def _risk_fit(stab: StabilityFeatures, profile: RiskProfile, family: str) -> float:
    """How well current conditions fit the active risk profile."""
    score = 100.0
    if stab.stability_score < profile.stability_floor:
        score -= (profile.stability_floor - stab.stability_score)
    if (_jump_safety(stab)) < profile.jump_safety_floor:
        score -= (profile.jump_safety_floor - _jump_safety(stab)) * 0.5
    # Family preference (soft): unlisted families lose some fit unless the
    # profile allows high-vol families.
    if profile.preferred_families and family:
        if not any(family.startswith(p) or p.startswith(family) for p in profile.preferred_families):
            score -= 0.0 if profile.allow_high_vol_families else 15.0
    return mathx.clamp(score, 0.0, 100.0)


def _deterioration_resistance(stab: StabilityFeatures) -> float:
    """Higher when the market is persistently stable and not decaying."""
    decay_pen = max(0.0, stab.score_decay_rate)      # positive decay is bad
    return mathx.clamp(0.7 * stab.stability_persistence + 0.3 * (1.0 - decay_pen)) * 100.0


def _danger_zscore(danger_count: int, n: int, p: float) -> float:
    """Binomial z-score of the observed danger-digit count vs expectation n*p.

    Self-calibrates to the configured danger_digits: at the uniform expectation
    z~0, so normal random clustering does not trip a veto; only a multi-sigma
    excess does.
    """
    if n <= 0:
        return 0.0
    mean = n * p
    sd = (n * p * (1.0 - p)) ** 0.5
    if sd <= 1e-9:
        return 0.0
    return (danger_count - mean) / sd


class ScoringEngine:
    def __init__(self, cfg: ScoringConfig, weights: Weights, profile: RiskProfile,
                 danger_digit_count: int = 3, entropy_floor: float = 2.6,
                 danger_z_short: float = 3.0, danger_z_primary: float = 3.0) -> None:
        self.cfg = cfg
        self.weights = weights
        self.profile = profile
        self.expected_danger = danger_digit_count / 10.0
        self.entropy_floor = entropy_floor
        # Sigma thresholds above the binomial expectation for digit vetoes.
        self.danger_z_short = danger_z_short
        self.danger_z_primary = danger_z_primary
        self._persistence: dict[str, int] = {}

    def score(
        self,
        bundle: FeatureBundle,
        stability: StabilityFeatures,
        family: str = "",
        deterioration_resist_override: float | None = None,
    ) -> MarketScore:
        pw, sw = self.cfg.primary_window, self.cfg.short_window
        d100 = bundle.digit[pw]
        d25 = bundle.digit[sw]
        m100 = bundle.movement[pw]

        sub = SubScores(
            digit_clean_100=_digit_cleanliness(
                d100.danger_pct, self.expected_danger, d100.cluster_score,
                d100.burst_count, d100.entropy, self.entropy_floor),
            digit_clean_25=_digit_cleanliness(
                d25.danger_pct, self.expected_danger, d25.cluster_score,
                d25.burst_count, d25.entropy, self.entropy_floor),
            movement_risk=_movement_safety(m100),
            accu_stability=stability.stability_score,
            jump_safety=_jump_safety(stability),
            trend_smooth=_trend_smoothness(stability, m100),
            risk_fit=_risk_fit(stability, self.profile, family),
            deterioration_resist=(
                deterioration_resist_override
                if deterioration_resist_override is not None
                else _deterioration_resistance(stability)
            ),
            data_quality=bundle.data_quality.quality_score,
        )

        mqs = round(self.weights.dot(sub.__dict__), 2)

        # --- veto layer: digit-risk and jump-risk act as SCREENING signals
        # that can force HIGH_RISK regardless of the weighted average.
        #
        # Digit vetoes are based on STATISTICAL SIGNIFICANCE, not raw counts:
        # for a well-behaved synthetic index the last digit is ~uniform, so
        # some clustering/bursting of danger digits happens purely by chance.
        # We veto only when the observed danger-digit count exceeds the binomial
        # expectation by several sigma (a genuine anomaly / feed problem), which
        # keeps digit-risk a rare, meaningful veto rather than constant noise.
        veto_reasons: list[str] = []
        p = self.expected_danger
        z25 = _danger_zscore(d25.danger_count, d25.count, p)
        z100 = _danger_zscore(d100.danger_count, d100.count, p)
        m25 = bundle.movement[sw]
        if z25 >= self.danger_z_short:
            veto_reasons.append("danger_digit_excess_25")
        if z100 >= self.danger_z_primary and d100.cluster_score >= 0.7:
            veto_reasons.append("danger_digit_cluster_100")
        if stability.jump_burst_prob >= 0.5:
            veto_reasons.append("jump_burst_probability")
        excess_tail_25 = max(0.0, m25.tail_ratio - 3.8)
        if excess_tail_25 / 6.0 >= 0.6 and m25.jump_count >= 1:
            veto_reasons.append("short_window_tail_jump")
        if bundle.data_quality.quality_score < 50.0 or not bundle.data_quality.fresh:
            veto_reasons.append("data_quality")

        status = self._status(mqs)
        if veto_reasons:
            status = Status.HIGH_RISK
            mqs = min(mqs, self.cfg.watch_threshold - 0.01)
        persistence = self._update_persistence(bundle.symbol, status)
        confidence = self._confidence(bundle, mqs)

        return MarketScore(
            symbol=bundle.symbol,
            epoch=bundle.epoch,
            mqs=mqs,
            sub_scores=sub,
            status=status,
            ready_persistence=persistence,
            suggested_growth_rate=0.01,           # filled by growth governor
            confidence=confidence,
            stability_score=stability.stability_score,
            danger_count=d100.danger_count,
            danger_pct=round(d100.danger_pct, 4),
            movement_risk_score=round(sub.movement_risk, 2),
            jump_risk_score=round(100.0 - sub.jump_safety, 2),
            trend_smooth_score=round(sub.trend_smooth, 2),
            data_quality_score=round(sub.data_quality, 2),
            veto_reasons=veto_reasons,
        )

    def _status(self, mqs: float) -> Status:
        if mqs >= self.cfg.ready_threshold:
            return Status.READY
        if mqs >= self.cfg.watch_threshold:
            return Status.WATCH
        return Status.HIGH_RISK

    def _update_persistence(self, symbol: str, status: Status) -> int:
        if status is Status.READY:
            self._persistence[symbol] = self._persistence.get(symbol, 0) + 1
        else:
            self._persistence[symbol] = 0
        return self._persistence[symbol]

    def _confidence(self, bundle: FeatureBundle, mqs: float) -> float:
        """0..1: scaled by data sufficiency and distance from a threshold."""
        primary = bundle.movement[self.cfg.primary_window]
        data_factor = mathx.clamp(primary.count / self.cfg.primary_window)
        # Distance of MQS from the nearer decision boundary (more decisive = higher).
        nearest = min(abs(mqs - self.cfg.ready_threshold), abs(mqs - self.cfg.watch_threshold))
        decisiveness = mathx.clamp(nearest / 25.0)
        dq = bundle.data_quality.quality_score / 100.0
        return round(mathx.clamp(0.5 * data_factor + 0.3 * decisiveness + 0.2 * dq), 3)

    def is_actionable(self, score: MarketScore) -> bool:
        """READY plus enough readiness persistence (anti-spike guard)."""
        return (
            score.status is Status.READY
            and score.ready_persistence >= self.cfg.min_ready_persistence_ticks
        )
