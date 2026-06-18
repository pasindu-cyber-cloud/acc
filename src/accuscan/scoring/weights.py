"""Scoring weights: load, validate, and normalise.

The Market Quality Score is a configurable weighted blend of nine sub-scores.
Weights are validated to be non-negative and are renormalised to sum to 1.0 so
a user can tweak individual weights without having to rebalance the rest.
"""

from __future__ import annotations

from dataclasses import dataclass

_FIELDS = (
    "digit_clean_100",
    "digit_clean_25",
    "movement_risk",
    "accu_stability",
    "jump_safety",
    "trend_smooth",
    "risk_fit",
    "deterioration_resist",
    "data_quality",
)

# Documented base weights (sum = 1.0). Mirror config/default.yaml.
DEFAULT_WEIGHTS = {
    "digit_clean_100": 0.15,
    "digit_clean_25": 0.10,
    "movement_risk": 0.15,
    "accu_stability": 0.20,
    "jump_safety": 0.15,
    "trend_smooth": 0.10,
    "risk_fit": 0.05,
    "deterioration_resist": 0.05,
    "data_quality": 0.05,
}


@dataclass
class Weights:
    values: dict[str, float]

    @classmethod
    def from_dict(cls, d: dict | None) -> "Weights":
        merged = dict(DEFAULT_WEIGHTS)
        if d:
            for k, v in d.items():
                if k in _FIELDS:
                    merged[k] = max(0.0, float(v))
        total = sum(merged.values()) or 1.0
        normalised = {k: v / total for k, v in merged.items()}
        return cls(values=normalised)

    def __getitem__(self, key: str) -> float:
        return self.values[key]

    def dot(self, sub: dict[str, float]) -> float:
        return sum(self.values[k] * sub.get(k, 0.0) for k in _FIELDS)
