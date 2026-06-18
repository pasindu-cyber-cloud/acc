"""Data models shared across modules (stdlib dataclasses, zero deps).

These are the contracts between transport, feature engine, scoring,
deterioration, health, execution and dashboard layers. `asdict_json` produces
JSON-safe dicts (enums -> their .value) for the dashboard and audit log.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .constants import AlertLevel, AlertReason, HealthLabel, Status


def asdict_json(obj: Any) -> Any:
    """Recursively convert dataclasses/enums/dicts/lists into JSON-safe data."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: asdict_json(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {(k.value if isinstance(k, Enum) else k): asdict_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [asdict_json(v) for v in obj]
    return obj


# --- Market data -------------------------------------------------------------
@dataclass
class Tick:
    symbol: str
    epoch: int
    quote: float
    pip_size: int = 2
    recv_ts: float = 0.0

    @property
    def last_digit(self) -> int:
        scaled = round(self.quote * (10 ** self.pip_size))
        return int(abs(scaled) % 10)


@dataclass
class SymbolInfo:
    symbol: str
    display_name: str = ""
    pip_size: int = 2
    accu_available: bool = False
    allowed_growth_rates: list[float] = field(default_factory=list)
    family: str = ""


# --- Features ----------------------------------------------------------------
@dataclass
class DigitFeatures:
    window: int
    count: int
    last_digit: int
    distribution: dict[int, float]
    danger_count: int
    danger_pct: float
    cluster_score: float
    burst_count: int
    drought_len: int
    entropy: float


@dataclass
class MovementFeatures:
    window: int
    count: int
    mean_abs_delta: float
    median_abs_delta: float
    std_delta: float
    norm_movement: float
    zero_move_count: int
    unit_move_count: int
    large_move_count: int
    rolling_range: float
    realized_vol: float
    jump_count: int
    jump_proxy: float
    avg_adverse_move: float
    movement_cluster: float
    trend_slope: float
    direction_persistence: float
    chop_score: float
    # Per-tick tail metrics — the primary accumulator knockout drivers, since
    # the barrier band is recalculated each tick around the previous spot.
    p95_abs_delta: float = 0.0
    p99_abs_delta: float = 0.0
    max_abs_delta: float = 0.0
    tail_ratio: float = 0.0          # p99(|delta|) / median(|delta|)


@dataclass
class StabilityFeatures:
    window: int
    mean_abs_move: float
    median_abs_move: float
    std_move: float
    rolling_range: float
    max_adverse_move: float
    jump_burst_prob: float
    micro_vol: float
    smoothness: float
    trend_consistency: float
    barrier_risk: float
    stability_persistence: float
    calmness: float
    score_decay_rate: float
    stability_score: float


@dataclass
class DataQuality:
    fresh: bool = True
    last_tick_age_ms: float = 0.0
    latency_ms: float = 0.0
    gap_count: int = 0
    quality_score: float = 100.0


# --- Scoring -----------------------------------------------------------------
@dataclass
class SubScores:
    digit_clean_100: float = 0.0
    digit_clean_25: float = 0.0
    movement_risk: float = 0.0
    accu_stability: float = 0.0
    jump_safety: float = 0.0
    trend_smooth: float = 0.0
    risk_fit: float = 0.0
    deterioration_resist: float = 0.0
    data_quality: float = 0.0


@dataclass
class MarketScore:
    symbol: str
    epoch: int
    mqs: float
    sub_scores: SubScores
    status: Status
    ready_persistence: int = 0
    suggested_growth_rate: float = 0.01
    confidence: float = 0.0
    stability_score: float = 0.0
    danger_count: int = 0
    danger_pct: float = 0.0
    movement_risk_score: float = 0.0
    jump_risk_score: float = 0.0
    trend_smooth_score: float = 0.0
    data_quality_score: float = 100.0
    veto_reasons: list[str] = field(default_factory=list)


# --- Deterioration / health --------------------------------------------------
@dataclass
class EntryBaseline:
    symbol: str
    epoch: int
    mqs: float
    stability: float
    volatility: float
    jump_risk: float
    trend_slope: float
    danger_rate: float
    movement_risk: float
    rolling_range: float
    data_quality: float


@dataclass
class DeteriorationResult:
    symbol: str
    epoch: int
    deterioration_score: float
    health_label: HealthLabel
    alert_level: AlertLevel
    recommended_action: str
    cusum: float = 0.0
    zscore: float = 0.0
    ewma_vol: float = 0.0
    score_drop: float = 0.0
    reasons: list[str] = field(default_factory=list)


@dataclass
class TradeHealth:
    symbol: str
    epoch: int
    health_score: float
    label: HealthLabel
    components: dict[str, float] = field(default_factory=dict)


@dataclass
class Alert:
    symbol: str
    epoch: int
    level: AlertLevel
    reason: AlertReason
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


# --- Execution ---------------------------------------------------------------
@dataclass
class Proposal:
    symbol: str
    contract_type: str = "ACCU"
    currency: str = "USD"
    amount: float = 1.0
    growth_rate: float = 0.01
    take_profit: float | None = None
    spot: float | None = None
    id: str | None = None


@dataclass
class OpenContract:
    contract_id: str
    symbol: str
    buy_price: float
    growth_rate: float
    entry_epoch: int
    take_profit: float | None = None
    current_spot: float | None = None
    profit: float = 0.0
    is_sold: bool = False
    status: str = "open"


@dataclass
class TradeRecord:
    symbol: str
    mode: str
    entry_epoch: int
    exit_epoch: int | None = None
    growth_rate: float = 0.01
    stake: float = 1.0
    take_profit: float | None = None
    pnl: float = 0.0
    exit_reason: str = ""
    entry_mqs: float = 0.0
    accepted: bool = True
    reject_reason: str = ""
