"""Execution layer: modes, safeguards, paper trader, demo/live trader."""

from .demo_trader import DemoLiveTrader, ExecutionResult
from .modes import ModeCapabilities, capabilities
from .paper_trader import PaperPosition, PaperTrader, band_halfwidth_pips
from .safeguards import SafeguardDecision, SafeguardEngine, SafeguardLimits

__all__ = [
    "capabilities",
    "ModeCapabilities",
    "SafeguardEngine",
    "SafeguardLimits",
    "SafeguardDecision",
    "PaperTrader",
    "PaperPosition",
    "band_halfwidth_pips",
    "DemoLiveTrader",
    "ExecutionResult",
]
