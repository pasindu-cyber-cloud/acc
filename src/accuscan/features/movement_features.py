"""Tick-to-tick movement features (stdlib only).

All movement is measured in *pips* (quote delta / pip_value) so thresholds are
comparable across symbols with different price scales.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import mathx
from ..models import MovementFeatures


@dataclass
class MovementConfig:
    zero_move_eps: float = 1e-9
    unit_move_pips: float = 1.0
    large_move_pips: float = 5.0
    jump_sigma: float = 4.0
    adverse_lookback: int = 100

    @classmethod
    def from_dict(cls, d: dict) -> "MovementConfig":
        return cls(
            zero_move_eps=float(d.get("zero_move_eps", 1e-9)),
            unit_move_pips=float(d.get("unit_move_pips", 1.0)),
            large_move_pips=float(d.get("large_move_pips", 5.0)),
            jump_sigma=float(d.get("jump_sigma", 4.0)),
            adverse_lookback=int(d.get("adverse_lookback", 100)),
        )


def compute_movement_features(
    deltas_pips: list[float],
    quotes_pips: list[float],
    window: int,
    cfg: MovementConfig,
) -> MovementFeatures:
    n = len(deltas_pips)
    if n == 0:
        return MovementFeatures(
            window=window, count=0, mean_abs_delta=0.0, median_abs_delta=0.0,
            std_delta=0.0, norm_movement=0.0, zero_move_count=0, unit_move_count=0,
            large_move_count=0, rolling_range=0.0, realized_vol=0.0, jump_count=0,
            jump_proxy=0.0, avg_adverse_move=0.0, movement_cluster=0.0,
            trend_slope=0.0, direction_persistence=0.0, chop_score=0.0,
        )

    abs_d = [abs(x) for x in deltas_pips]
    mean_abs = mathx.mean(abs_d)
    median_abs = mathx.median(abs_d)
    std_d = mathx.std(deltas_pips, ddof=0)
    realized_vol = std_d

    zero_move = sum(1 for a in abs_d if a <= cfg.zero_move_eps)
    unit_move = sum(1 for a in abs_d if cfg.zero_move_eps < a < cfg.large_move_pips)
    large_move = sum(1 for a in abs_d if a >= cfg.large_move_pips)

    rolling_range = (max(quotes_pips) - min(quotes_pips)) if quotes_pips else 0.0

    jump_thresh = cfg.jump_sigma * std_d if std_d > 0 else float("inf")
    jump_flags = [a > jump_thresh for a in abs_d]
    jump_count = sum(1 for f in jump_flags if f)
    energy = sum(a * a for a in abs_d)
    jump_energy = sum(abs_d[i] ** 2 for i in range(n) if jump_flags[i])
    jump_proxy = mathx.safe_div(jump_energy, energy, 0.0)

    look = deltas_pips[-cfg.adverse_lookback:]
    cum = mathx.cumsum(look)
    rmax = mathx.running_max(cum)
    drawdown = [rmax[i] - cum[i] for i in range(len(cum))]
    avg_adverse_move = mathx.mean(drawdown) if drawdown else 0.0

    movement_cluster = max(0.0, mathx.lag1_autocorr(abs_d))

    trend_slope = mathx.linreg_slope(quotes_pips) if quotes_pips else 0.0

    signs = [(1 if x > 0 else (-1 if x < 0 else 0)) for x in deltas_pips]
    nonzero = [s for s in signs if s != 0]
    if len(nonzero) >= 2:
        same = sum(1 for i in range(1, len(nonzero)) if nonzero[i] == nonzero[i - 1])
        flips = len(nonzero) - 1 - same
        direction_persistence = same / (len(nonzero) - 1)
        chop_score = flips / (len(nonzero) - 1)
    else:
        direction_persistence = 0.0
        chop_score = 0.0

    norm_movement = mathx.safe_div(mean_abs, rolling_range + 1e-9, 0.0)

    # Per-tick tail metrics: the band is recalculated each tick around the
    # previous spot, so knockout risk is dominated by the upper tail of |delta|
    # relative to the *typical* |delta| (a volatility-band proxy). For a normal
    # distribution p99/median ~ 3.8; materially higher implies jump/fat-tail risk.
    p95 = mathx.percentile(abs_d, 95.0)
    p99 = mathx.percentile(abs_d, 99.0)
    max_abs = max(abs_d) if abs_d else 0.0
    typical = median_abs if median_abs > 0 else (mean_abs if mean_abs > 0 else 1e-9)
    tail_ratio = p99 / typical

    return MovementFeatures(
        window=window,
        count=n,
        mean_abs_delta=mean_abs,
        median_abs_delta=median_abs,
        std_delta=std_d,
        norm_movement=norm_movement,
        zero_move_count=zero_move,
        unit_move_count=unit_move,
        large_move_count=large_move,
        rolling_range=rolling_range,
        realized_vol=realized_vol,
        jump_count=jump_count,
        jump_proxy=jump_proxy,
        avg_adverse_move=avg_adverse_move,
        movement_cluster=movement_cluster,
        trend_slope=trend_slope,
        direction_persistence=direction_persistence,
        chop_score=chop_score,
        p95_abs_delta=p95,
        p99_abs_delta=p99,
        max_abs_delta=max_abs,
        tail_ratio=tail_ratio,
    )
