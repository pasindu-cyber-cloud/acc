"""Baseline manager: learns normal per-executable behaviour and computes Z-scores.

For every executable identity (``ProcessSnapshot.identity_key``) ProcAI maintains
running statistics for a set of behavioural metrics using **Welford's online
algorithm**. This is O(1) memory per metric and never stores raw history, which
is both efficient and privacy-friendly.

Given a fresh snapshot, :meth:`BaselineManager.deviation` reports the Z-score of
each metric relative to its learned mean/standard deviation. Large absolute
Z-scores indicate the process is behaving unusually *for itself* -- a powerful,
context-aware complement to static thresholds.

**Learning mode**: during an initial observation window ProcAI only *learns* and
suppresses deviation-driven alerts, so it can establish what "normal" looks like
on this particular machine before becoming stricter.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Optional

from .features import extract
from .models import BaselineDeviation, ProcessSnapshot
from ..data.database import Database
from ..utils.logging_setup import get_logger

log = get_logger("core.baseline")

# Metrics tracked in the baseline (subset of features that vary meaningfully).
BASELINE_METRICS: tuple[str, ...] = (
    "cpu_percent",
    "memory_percent",
    "memory_mb",
    "num_threads",
    "num_connections",
)


@dataclass
class RunningStat:
    """Welford running statistics for a single metric."""

    count: int = 0
    mean: float = 0.0
    m2: float = 0.0
    min_value: float = math.inf
    max_value: float = -math.inf

    def update(self, x: float) -> None:
        self.count += 1
        delta = x - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (x - self.mean)
        self.min_value = min(self.min_value, x)
        self.max_value = max(self.max_value, x)

    @property
    def variance(self) -> float:
        return self.m2 / (self.count - 1) if self.count > 1 else 0.0

    @property
    def std(self) -> float:
        return math.sqrt(self.variance)

    def zscore(self, x: float, *, rel_floor: float = 0.05, cap: float = 12.0) -> float:
        """Z-score of x, robust and bounded.

        A metric that has been perfectly (or nearly) constant has std ~ 0, which
        would otherwise make any change look infinitely anomalous. We therefore
        floor the standard deviation to a small fraction of the mean (or 1.0,
        whichever is larger) and clamp the result to +/- ``cap`` so a single
        metric can never dominate the downstream score with a pathological value.
        """
        if self.count < 2:
            return 0.0
        std = max(self.std, abs(self.mean) * rel_floor, 1.0)
        z = (x - self.mean) / std
        return max(-cap, min(cap, z))


class BaselineManager:
    """Loads/updates per-executable baselines backed by the database."""

    def __init__(self, db: Database, *, min_samples: int = 8) -> None:
        self.db = db
        self.min_samples = min_samples
        # In-memory cache: identity_key -> {metric -> RunningStat}
        self._cache: dict[str, dict[str, RunningStat]] = {}

    # ------------------------------------------------------------------ #
    def _load_stats(self, identity: str) -> dict[str, RunningStat]:
        if identity in self._cache:
            return self._cache[identity]
        stats: dict[str, RunningStat] = {}
        for metric in BASELINE_METRICS:
            row = self.db.get_baseline(identity, metric)
            if row:
                stats[metric] = RunningStat(
                    count=row["count"], mean=row["mean"], m2=row["m2"],
                    min_value=row["min_value"], max_value=row["max_value"],
                )
            else:
                stats[metric] = RunningStat()
        self._cache[identity] = stats
        return stats

    def _persist(self, identity: str, stats: dict[str, RunningStat]) -> None:
        for metric, st in stats.items():
            self.db.upsert_baseline(
                identity, metric, st.count, st.mean, st.m2,
                0.0 if st.min_value is math.inf else st.min_value,
                0.0 if st.max_value == -math.inf else st.max_value,
            )

    # ------------------------------------------------------------------ #
    def update(self, snap: ProcessSnapshot, *, persist: bool = True) -> None:
        """Fold one snapshot into the baseline for its executable."""
        identity = snap.identity_key()
        if not identity:
            return
        feats = extract(snap)
        stats = self._load_stats(identity)
        for metric in BASELINE_METRICS:
            stats[metric].update(float(feats.get(metric, 0.0)))
        if persist:
            self._persist(identity, stats)

    def update_many(self, snaps: list[ProcessSnapshot]) -> None:
        for s in snaps:
            self.update(s, persist=False)
        # Persist once per identity touched.
        for identity in {s.identity_key() for s in snaps if s.identity_key()}:
            self._persist(identity, self._cache[identity])

    # ------------------------------------------------------------------ #
    def deviation(self, snap: ProcessSnapshot) -> BaselineDeviation:
        """Compute the Z-score deviation of a snapshot from its baseline."""
        identity = snap.identity_key()
        stats = self._load_stats(identity)
        # Use the smallest sample count across metrics as the "maturity" figure.
        samples = min((stats[m].count for m in BASELINE_METRICS), default=0)
        if samples < self.min_samples:
            return BaselineDeviation(available=False, samples=samples)

        feats = extract(snap)
        z_scores: dict[str, float] = {}
        for metric in BASELINE_METRICS:
            z_scores[metric] = round(stats[metric].zscore(float(feats.get(metric, 0.0))), 3)

        deviating = [m for m, z in z_scores.items() if abs(z) >= 3.0]
        max_abs = max((abs(z) for z in z_scores.values()), default=0.0)
        return BaselineDeviation(
            available=True,
            samples=samples,
            z_scores=z_scores,
            max_abs_z=round(max_abs, 3),
            deviating_metrics=deviating,
        )

    # ------------------------------------------------------------------ #
    def identity_maturity(self, identity: str) -> int:
        stats = self._load_stats(identity)
        return min((stats[m].count for m in BASELINE_METRICS), default=0)

    def reset_cache(self) -> None:
        self._cache.clear()


class LearningMode:
    """Tracks whether ProcAI is still in its initial observation window.

    During learning mode the engine still computes everything (so the user sees
    activity) but the hybrid engine treats baseline-deviation contributions as
    informational rather than alert-worthy.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def start(self, duration_minutes: int) -> None:
        self.db.set_setting("learning_started_at", time.time())
        self.db.set_setting("learning_duration_minutes", duration_minutes)
        log.info("Learning mode started for %d minutes.", duration_minutes)

    def remaining_seconds(self) -> float:
        started = self.db.get_setting("learning_started_at")
        duration = self.db.get_setting("learning_duration_minutes")
        if not started or not duration:
            return 0.0
        elapsed = time.time() - float(started)
        return max(0.0, float(duration) * 60.0 - elapsed)

    def is_active(self) -> bool:
        return self.remaining_seconds() > 0.0
