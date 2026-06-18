"""Project-wide constants and enums.

Product/API constants are anchored to Deriv official documentation:
  - contract_type for Accumulators is "ACCU"
    (https://legacy-docs.deriv.com/docs/accumulator-options)
  - growth_rate values: 0.01, 0.02, 0.03, 0.04, 0.05 (1%-5%)
    (https://deriv.com/trading-terms-glossary)
  - Accumulators have NO stop loss; only take_profit via limit_order.
  - Max contract duration is broker-defined (~230 ticks historically).
Where any of these differ between new docs (developers.deriv.com) and legacy
docs (legacy-docs.deriv.com), the transport layer normalises the difference.
"""

from __future__ import annotations

from enum import Enum

# --- Deriv product constants -------------------------------------------------
ACCU_CONTRACT_TYPE = "ACCU"
ALLOWED_GROWTH_RATES: tuple[float, ...] = (0.01, 0.02, 0.03, 0.04, 0.05)
DEFAULT_WS_URL = "wss://ws.derivws.com/websockets/v3"
DEFAULT_APP_ID = "1089"  # public demo app_id; replace with your own.

# Last-digit space for synthetic indices.
DIGITS: tuple[int, ...] = tuple(range(10))


class Mode(str, Enum):
    """Execution mode. Order matters: each later mode is strictly more powerful."""

    ANALYTICS = "analytics"
    PAPER = "paper"
    DEMO = "demo"
    LIVE = "live"


class RiskProfileName(str, Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class Status(str, Enum):
    """Market readiness status derived from the Market Quality Score."""

    READY = "READY"
    WATCH = "WATCH"
    HIGH_RISK = "HIGH_RISK"


class HealthLabel(str, Enum):
    HEALTHY = "HEALTHY"
    WATCH_CLOSELY = "WATCH_CLOSELY"
    DETERIORATING = "DETERIORATING"
    CRITICAL = "CRITICAL"
    EXIT_IF_POSSIBLE = "EXIT_IF_POSSIBLE"


class AlertLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertReason(str, Enum):
    JUMP_BURST = "jump_burst"
    VOLATILITY_EXPANSION = "volatility_expansion"
    DANGER_DIGIT_CLUSTER = "danger_digit_cluster"
    SHORT_WINDOW_DEGRADATION = "short_window_degradation"
    TREND_REVERSAL = "trend_reversal"
    SCORE_COLLAPSE = "score_collapse"
    DATA_STALENESS = "data_staleness"
    LATENCY = "latency"
    CONTRACT_HEALTH = "contract_health"
    READINESS_TOO_BRIEF = "readiness_too_brief"


class DataSource(str, Enum):
    DERIV = "deriv"
    MOCK = "mock"
    REPLAY = "replay"


# Sentinel for "live trading explicitly confirmed".
LIVE_CONFIRM_TOKEN = "I_UNDERSTAND_THE_RISK"
