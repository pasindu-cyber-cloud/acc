"""Accumulator Stability Model.

Estimates how suitable the *current* market is for Accumulator contracts.

KEY DESIGN CHOICE — relative/adaptive normalisation
---------------------------------------------------
Accumulator economics: each tick that the spot stays inside a (broker-set)
barrier band compounds the payout by the growth rate; a single breach loses the
stake. The implied barrier width *shrinks as the growth rate rises*. So
"suitability" is fundamentally about how small and well-behaved tick movement
is **relative to the room available**, plus how rarely large/jumpy moves occur.

Because absolute pip magnitudes differ wildly across symbols (and between mock
and live feeds), every sub-metric here is normalised against a *self-referential*
scale derived from the symbol's own longer window — never a hard-coded pip
constant. Optional `ref_*` config values only act as soft anchors.

All outputs are bounded to sane ranges; the headline `stability_score` is 0..100
where higher = calmer / more accumulator-friendly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .. import mathx
from ..features.feature_engine import FeatureBundle
from ..models import StabilityFeatures


@dataclass
class StabilityConfig:
    primary_window: int = 100
    short_window: int = 25
    long_window: int = 1000
    ref_abs_move_pips: float = 2.0
    ref_range_pips: float = 30.0
    ref_micro_vol_pips: float = 1.5
    smoothness_halflife: int = 25

    @classmethod
    def from_dict(cls, scanner: dict, stability: dict) -> "StabilityConfig":
        return cls(
            primary_window=int(scanner.get("primary_window", 100)),
            short_window=25,
            long_window=max(scanner.get("windows", [1000])),
            ref_abs_move_pips=float(stability.get("ref_abs_move_pips", 2.0)),
            ref_range_pips=float(stability.get("ref_range_pips", 30.0)),
            ref_micro_vol_pips=float(stability.get("ref_micro_vol_pips", 1.5)),
            smoothness_halflife=int(stability.get("smoothness_halflife", 25)),
        )


# Growth rate -> approximate relative barrier tightness multiplier. Higher
# growth rates imply tighter bands, so the same movement is riskier. These are
# monotone, conservative heuristics (validate/replace via replay).
_GROWTH_TIGHTNESS = {0.01: 1.00, 0.02: 1.35, 0.03: 1.75, 0.04: 2.20, 0.05: 2.75}


def growth_tightness(growth_rate: float) -> float:
    # Nearest configured rate.
    key = min(_GROWTH_TIGHTNESS, key=lambda r: abs(r - growth_rate))
    return _GROWTH_TIGHTNESS[key]


class StabilityModel:
    def __init__(self, cfg: StabilityConfig) -> None:
        self.cfg = cfg

    def compute(
        self,
        bundle: FeatureBundle,
        growth_rate: float = 0.01,
    ) -> StabilityFeatures:
        c = self.cfg
        pw, sw, lw = c.primary_window, c.short_window, c.long_window
        m = bundle.movement.get(pw)
        m_short = bundle.movement.get(sw)
        m_long = bundle.movement.get(lw) or m

        if m is None or m.count == 0:
            return _empty_stability(pw)

        mean_abs = m.mean_abs_delta
        median_abs = m.median_abs_delta
        std_move = m.std_delta
        rolling_range = m.rolling_range
        max_adverse = m.avg_adverse_move

        # --- per-tick tail risk: THE primary accumulator knockout driver -----
        # The barrier band is recalculated each tick around the previous spot
        # and is calibrated to the symbol's normal volatility. Knockout happens
        # when a single tick's |delta| exceeds the band, i.e. when the UPPER
        # TAIL of per-tick moves is large relative to the typical move.
        # Gaussian baseline p99/median ~ 3.8; excess above that = fat tails/jumps.
        gauss_baseline = 3.8
        excess_tail = max(0.0, m.tail_ratio - gauss_baseline)
        tail_risk = mathx.clamp(excess_tail / 6.0)
        large_freq = m.large_move_count / max(m.count, 1)

        # Self-referential scale for micro-vol normalisation.
        base_scale = max(m_long.mean_abs_delta if m_long else mean_abs, 1e-9)
        micro_vol = (m_short.std_delta if m_short else std_move)
        micro_vol_ratio = micro_vol / base_scale

        # --- jump burst probability proxy: tail + clustering + tail energy ---
        jump_burst_prob = mathx.clamp(
            0.55 * tail_risk + 0.25 * m.jump_proxy + 0.20 * m.movement_cluster
        )

        # --- barrier risk proxy: core tail/jump risk amplified by how tight the
        # band is for the chosen growth rate (higher growth => narrower band).
        core_risk = mathx.clamp(
            0.60 * tail_risk + 0.25 * m.jump_proxy + 0.15 * mathx.clamp(large_freq * 8.0)
        )
        growth_pressure = mathx.clamp((growth_rate - 0.01) / 0.04)   # 0 at 1%, 1 at 5%
        barrier_risk = mathx.clamp(core_risk * (0.6 + 0.4 * growth_pressure) + 0.15 * growth_pressure)

        # --- smoothness / trend (secondary; affect TP dynamics, not knockout) -
        smoothness = mathx.clamp(1.0 - micro_vol_ratio / 2.5)
        trend_consistency = mathx.clamp(m.direction_persistence)

        # --- calmness: small, untailed, unclustered per-tick moves ------------
        calmness = mathx.clamp(1.0 - 0.7 * tail_risk - 0.3 * m.movement_cluster)

        # --- stability persistence: short vs primary volatility agreement -----
        if m_short and m_short.std_delta > 0 and std_move > 0:
            ratio = std_move / m_short.std_delta
            stability_persistence = mathx.clamp(1.0 - abs(math.log(ratio + 1e-9)))
        else:
            stability_persistence = 0.5

        # --- score decay rate: short-window vol expansion vs primary ----------
        short_vol = m_short.std_delta if m_short else std_move
        score_decay_rate = mathx.clamp((short_vol - std_move) / (std_move + 1e-9), -1.0, 1.0)

        # --- headline stability score (0..100), barrier/jump dominated --------
        raw = (
            0.35 * (1.0 - barrier_risk)
            + 0.30 * calmness
            + 0.15 * stability_persistence
            + 0.10 * (1.0 - jump_burst_prob)
            + 0.10 * smoothness
        )
        raw *= (1.0 - 0.4 * jump_burst_prob)        # extra jump penalty
        stability_score = round(mathx.clamp(raw) * 100.0, 2)

        return StabilityFeatures(
            window=pw,
            mean_abs_move=mean_abs,
            median_abs_move=median_abs,
            std_move=std_move,
            rolling_range=rolling_range,
            max_adverse_move=max_adverse,
            jump_burst_prob=jump_burst_prob,
            micro_vol=micro_vol,
            smoothness=smoothness,
            trend_consistency=trend_consistency,
            barrier_risk=barrier_risk,
            stability_persistence=stability_persistence,
            calmness=calmness,
            score_decay_rate=score_decay_rate,
            stability_score=stability_score,
        )


def _empty_stability(window: int) -> StabilityFeatures:
    return StabilityFeatures(
        window=window, mean_abs_move=0.0, median_abs_move=0.0, std_move=0.0,
        rolling_range=0.0, max_adverse_move=0.0, jump_burst_prob=0.0, micro_vol=0.0,
        smoothness=0.0, trend_consistency=0.0, barrier_risk=1.0,
        stability_persistence=0.0, calmness=0.0, score_decay_rate=0.0,
        stability_score=0.0,
    )
