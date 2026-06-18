"""Backtesting / replay package."""

from .metrics import TickRecord, compute_metrics, danger_onsets
from .replay_engine import ReplayEngine, compare_profiles
from .synthetic import Scenario, Segment, build_scenario, default_scenario

__all__ = [
    "ReplayEngine",
    "compare_profiles",
    "Scenario",
    "Segment",
    "build_scenario",
    "default_scenario",
    "TickRecord",
    "compute_metrics",
    "danger_onsets",
]
