"""Feature Engine package: rolling windows, digit and movement features."""

from .digit_features import DigitConfig, compute_digit_features, shannon_entropy
from .feature_engine import FeatureBundle, FeatureEngine
from .movement_features import MovementConfig, compute_movement_features
from .windows import SymbolBuffer

__all__ = [
    "SymbolBuffer",
    "DigitConfig",
    "MovementConfig",
    "compute_digit_features",
    "compute_movement_features",
    "shannon_entropy",
    "FeatureEngine",
    "FeatureBundle",
]
