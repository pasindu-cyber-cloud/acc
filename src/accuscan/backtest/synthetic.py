"""Synthetic scenario generation for backtesting.

Builds reproducible price paths stitched from labelled regime segments, where
each tick carries a ground-truth "danger" label (True during VOLATILE / JUMPY
segments). The labels let the replay engine measure false positives/negatives
and alert lead time against a known truth.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class Segment:
    regime: str          # CALM | TRENDING | VOLATILE | JUMPY
    length: int


@dataclass
class Scenario:
    symbol: str
    pip_size: int
    prices: list[float]
    danger: list[bool]   # ground-truth label per tick
    regimes: list[str]   # regime per tick


_DANGER_REGIMES = {"VOLATILE", "JUMPY"}


def build_scenario(
    symbol: str,
    segments: list[Segment],
    *,
    sigma: float = 0.1,
    pip_size: int = 4,
    seed: int = 0,
    start: float = 1000.0,
) -> Scenario:
    rng = random.Random(seed)
    price = start
    prices: list[float] = []
    danger: list[bool] = []
    regimes: list[str] = []
    for seg in segments:
        for _ in range(seg.length):
            inc = rng.gauss(0.0, sigma)
            if seg.regime == "TRENDING":
                inc += sigma * 0.4
            elif seg.regime == "VOLATILE":
                inc *= 2.4
            elif seg.regime == "JUMPY":
                if rng.random() < 0.06:
                    inc += rng.choice((-1, 1)) * sigma * 16
            price = max(price + inc, 10 ** (-pip_size))
            prices.append(round(price, pip_size))
            danger.append(seg.regime in _DANGER_REGIMES)
            regimes.append(seg.regime)
    return Scenario(symbol=symbol, pip_size=pip_size, prices=prices, danger=danger, regimes=regimes)


def default_scenario(symbol: str = "R_25", seed: int = 42) -> Scenario:
    """A standard calm -> danger -> calm -> danger profile for demos/tests."""
    segments = [
        Segment("CALM", 400),
        Segment("VOLATILE", 150),
        Segment("CALM", 350),
        Segment("JUMPY", 150),
        Segment("CALM", 300),
    ]
    return build_scenario(symbol, segments, sigma=0.06, pip_size=4, seed=seed)
