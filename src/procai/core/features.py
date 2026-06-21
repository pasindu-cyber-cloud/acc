"""Feature extraction: ProcessSnapshot -> numeric feature dict.

A single, stable feature definition is used by the rule engine, the ML model and
the simulation data generator so training and inference always agree. Features
are deliberately interpretable (raw and lightly-derived behavioural quantities),
which keeps the whole detector explainable.

``FEATURE_NAMES`` defines the canonical order used when building vectors for
scikit-learn. Keep additions append-only so previously trained models remain
compatible (or retrain on change).
"""

from __future__ import annotations

import math

from .models import ProcessSnapshot

FEATURE_NAMES: tuple[str, ...] = (
    "cpu_percent",
    "memory_percent",
    "memory_mb",
    "num_threads",
    "num_connections",
    "num_remote_endpoints",
    "lifetime_minutes",
    "is_unsigned",
    "in_suspicious_dir",
    "is_startup_persistent",
    "log_memory_mb",
    "log_threads",
    "conn_per_minute",
    "cmdline_length",
)


def extract(snap: ProcessSnapshot) -> dict[str, float]:
    """Return the canonical feature dict for one snapshot."""
    lifetime_min = max(snap.lifetime_seconds / 60.0, 0.0)
    mem_mb = snap.memory_mb
    # is_signed may be None (unknown) -> treat unknown as "not a positive signal"
    is_unsigned = 1.0 if snap.is_signed is False else 0.0
    conn_per_min = snap.num_connections / lifetime_min if lifetime_min > 0.5 else float(
        snap.num_connections
    )
    return {
        "cpu_percent": float(snap.cpu_percent),
        "memory_percent": float(snap.memory_percent),
        "memory_mb": float(mem_mb),
        "num_threads": float(snap.num_threads),
        "num_connections": float(snap.num_connections),
        "num_remote_endpoints": float(snap.num_remote_endpoints),
        "lifetime_minutes": float(lifetime_min),
        "is_unsigned": is_unsigned,
        "in_suspicious_dir": 1.0 if snap.in_suspicious_dir else 0.0,
        "is_startup_persistent": 1.0 if snap.is_startup_persistent else 0.0,
        "log_memory_mb": math.log1p(max(mem_mb, 0.0)),
        "log_threads": math.log1p(max(snap.num_threads, 0)),
        "conn_per_minute": float(conn_per_min),
        "cmdline_length": float(len(snap.cmdline or "")),
    }


def to_vector(features: dict[str, float]) -> list[float]:
    """Order a feature dict into the canonical vector for ML."""
    return [float(features.get(name, 0.0)) for name in FEATURE_NAMES]
