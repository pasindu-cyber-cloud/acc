"""Small, dependency-free numeric helpers.

AccuScan's core engine deliberately avoids numpy/pandas so it runs anywhere
(including restricted/offline environments) and stays trivially testable. If
you deploy at very high symbol counts and want vectorised performance, the
feature functions are isolated enough to swap for numpy implementations.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def median(xs: Sequence[float]) -> float:
    n = len(xs)
    if n == 0:
        return 0.0
    s = sorted(xs)
    mid = n // 2
    if n % 2:
        return float(s[mid])
    return (s[mid - 1] + s[mid]) / 2.0


def variance(xs: Sequence[float], ddof: int = 0) -> float:
    n = len(xs)
    if n - ddof <= 0:
        return 0.0
    m = mean(xs)
    return sum((x - m) ** 2 for x in xs) / (n - ddof)


def std(xs: Sequence[float], ddof: int = 0) -> float:
    return math.sqrt(variance(xs, ddof))


def diff(xs: Sequence[float]) -> list[float]:
    return [xs[i] - xs[i - 1] for i in range(1, len(xs))]


def cumsum(xs: Sequence[float]) -> list[float]:
    out: list[float] = []
    total = 0.0
    for x in xs:
        total += x
        out.append(total)
    return out


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b else default


def linreg_slope(y: Sequence[float]) -> float:
    """OLS slope of y against its index (0..n-1)."""
    n = len(y)
    if n < 2:
        return 0.0
    xs = list(range(n))
    xbar = (n - 1) / 2.0
    ybar = mean(y)
    denom = sum((x - xbar) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    num = sum((xs[i] - xbar) * (y[i] - ybar) for i in range(n))
    return num / denom


def lag1_autocorr(xs: Sequence[float]) -> float:
    """Pearson autocorrelation at lag 1, in [-1, 1]; 0 if undefined."""
    n = len(xs)
    if n < 3:
        return 0.0
    a = xs[:-1]
    b = xs[1:]
    abar = mean(a)
    bbar = mean(b)
    num = sum((a[i] - abar) * (b[i] - bbar) for i in range(len(a)))
    da = math.sqrt(sum((x - abar) ** 2 for x in a))
    db = math.sqrt(sum((x - bbar) ** 2 for x in b))
    if da == 0 or db == 0:
        return 0.0
    return num / (da * db)


def shannon_entropy_bits(probs: Sequence[float]) -> float:
    h = 0.0
    for p in probs:
        if p > 0:
            h -= p * math.log2(p)
    return h


def bincount10(digits: Sequence[int]) -> list[int]:
    counts = [0] * 10
    for d in digits:
        if 0 <= d <= 9:
            counts[d] += 1
    return counts


def running_max(xs: Sequence[float]) -> list[float]:
    out: list[float] = []
    cur = -math.inf
    for x in xs:
        cur = max(cur, x)
        out.append(cur)
    return out


def percentile(xs: Sequence[float], p: float) -> float:
    """Linear-interpolation percentile, p in [0,100]."""
    if not xs:
        return 0.0
    s = sorted(xs)
    if len(s) == 1:
        return float(s[0])
    rank = (p / 100.0) * (len(s) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return float(s[lo])
    frac = rank - lo
    return float(s[lo] * (1 - frac) + s[hi] * frac)
