"""Last-digit features (stdlib only).

IMPORTANT MODELLING NOTE
------------------------
Digit-risk is treated as a CONFIGURABLE SCREENING / VETO signal, NOT the sole
alpha source. For a well-behaved synthetic index the last digit is, by design,
close to uniform; persistent deviations are therefore mostly useful as a
data-quality / regime-change tripwire and must be validated via replay.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import mathx
from ..constants import DIGITS
from ..models import DigitFeatures


@dataclass
class DigitConfig:
    danger_digits: tuple[int, ...] = (0, 1, 5)
    cluster_distance: int = 3
    burst_threshold: int = 3
    drought_threshold: int = 40
    entropy_floor: float = 2.6

    @classmethod
    def from_dict(cls, d: dict) -> "DigitConfig":
        return cls(
            danger_digits=tuple(d.get("danger_digits", (0, 1, 5))),
            cluster_distance=int(d.get("cluster_distance", 3)),
            burst_threshold=int(d.get("burst_threshold", 3)),
            drought_threshold=int(d.get("drought_threshold", 40)),
            entropy_floor=float(d.get("entropy_floor", 2.6)),
        )


def shannon_entropy(distribution: dict[int, float]) -> float:
    """Entropy in bits of a digit distribution (max = log2(10) ~ 3.3219)."""
    return mathx.shannon_entropy_bits(list(distribution.values()))


def compute_digit_features(digits: list[int], window: int, cfg: DigitConfig) -> DigitFeatures:
    n = len(digits)
    if n == 0:
        return DigitFeatures(
            window=window, count=0, last_digit=-1,
            distribution={d: 0.0 for d in DIGITS},
            danger_count=0, danger_pct=0.0, cluster_score=0.0,
            burst_count=0, drought_len=0, entropy=0.0,
        )

    counts = mathx.bincount10(digits)
    distribution = {int(d): counts[d] / n for d in DIGITS}

    danger_set = set(cfg.danger_digits)
    danger_idx = [i for i, d in enumerate(digits) if d in danger_set]
    danger_count = len(danger_idx)
    danger_pct = danger_count / n

    # Clustering: share of consecutive danger-digit gaps <= cluster_distance.
    cluster_score = 0.0
    burst_count = 0
    if danger_count >= 2:
        gaps = [danger_idx[i] - danger_idx[i - 1] for i in range(1, danger_count)]
        close = [1 for g in gaps if g <= cfg.cluster_distance]
        cluster_score = len(close) / len(gaps)
        for i in range(danger_count):
            lo = danger_idx[i]
            hi = lo + cfg.cluster_distance
            in_win = sum(1 for j in danger_idx if lo <= j <= hi)
            if in_win >= cfg.burst_threshold:
                burst_count += 1

    # Drought: trailing ticks with no danger digit.
    drought_len = 0
    for d in reversed(digits):
        if d in danger_set:
            break
        drought_len += 1

    entropy = shannon_entropy(distribution)

    return DigitFeatures(
        window=window,
        count=n,
        last_digit=int(digits[-1]),
        distribution=distribution,
        danger_count=danger_count,
        danger_pct=danger_pct,
        cluster_score=cluster_score,
        burst_count=burst_count,
        drought_len=drought_len,
        entropy=entropy,
    )
