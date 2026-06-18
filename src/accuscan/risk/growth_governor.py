"""Adaptive Growth-Rate Governor.

Recommends an Accumulator growth rate from CURRENT market conditions — never
simply the maximum a risk profile allows. Because a higher growth rate implies
a narrower per-tick barrier band, the governor only steps the rate up when the
market is calm and jump-free enough to absorb the tighter band.

Method: evaluate each allowed rate (ascending, capped by the profile) by
re-running the stability model at that rate; pick the HIGHEST rate that still
satisfies the profile's stability and jump-safety floors with a safety margin,
and where recent deterioration is low. Defaults to the minimum rate otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import RiskProfile
from ..constants import ALLOWED_GROWTH_RATES
from ..features.feature_engine import FeatureBundle
from ..stability.stability_model import StabilityModel


@dataclass
class GrowthRecommendation:
    growth_rate: float
    rationale: str
    evaluated: dict[float, dict]   # rate -> {stability, jump_safety, barrier_risk, ok}


class GrowthGovernor:
    def __init__(
        self,
        allowed_rates: tuple[float, ...] = ALLOWED_GROWTH_RATES,
        stability_margin: float = 5.0,
        max_deterioration: float = 30.0,
    ) -> None:
        self.allowed_rates = tuple(sorted(allowed_rates))
        self.stability_margin = stability_margin
        self.max_deterioration = max_deterioration

    def recommend(
        self,
        bundle: FeatureBundle,
        stability_model: StabilityModel,
        profile: RiskProfile,
        deterioration_score: float = 0.0,
    ) -> GrowthRecommendation:
        candidates = [r for r in self.allowed_rates if r <= profile.max_growth_rate + 1e-9]
        if not candidates:
            candidates = [self.allowed_rates[0]]

        evaluated: dict[float, dict] = {}
        best = candidates[0]
        for rate in candidates:
            st = stability_model.compute(bundle, growth_rate=rate)
            jump_safety = (1.0 - st.jump_burst_prob) * 100.0
            ok = (
                st.stability_score >= profile.stability_floor + self.stability_margin
                and jump_safety >= profile.jump_safety_floor
                and deterioration_score <= self.max_deterioration
            )
            evaluated[rate] = {
                "stability": round(st.stability_score, 2),
                "jump_safety": round(jump_safety, 2),
                "barrier_risk": round(st.barrier_risk, 3),
                "ok": ok,
            }
            if ok:
                best = rate   # keep stepping up while conditions allow

        if any(v["ok"] for v in evaluated.values()):
            rationale = (
                f"highest rate satisfying stability>= "
                f"{profile.stability_floor + self.stability_margin:.0f} and "
                f"jump_safety>={profile.jump_safety_floor:.0f} "
                f"(deterioration {deterioration_score:.0f})"
            )
        else:
            best = candidates[0]
            rationale = (
                "no rate met stability/jump floors; defaulting to minimum "
                f"{best:.2f} (conditions not strong enough for higher growth)"
            )
        return GrowthRecommendation(growth_rate=best, rationale=rationale, evaluated=evaluated)
