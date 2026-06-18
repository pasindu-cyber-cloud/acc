"""Execution Safeguards.

A single gate every entry must pass. ALL checks are AND-ed; any failure blocks
the trade and is logged with a machine-readable reason. Safeguards are stateful
(they count trades, track losses and cooldowns) and are mode-agnostic: paper,
demo and live all go through the same gate so behaviour is identical and
testable offline.

Hard rules enforced here (never overridable by a risk profile):
  - only enter when status is READY with sufficient readiness persistence
  - data quality must be healthy and the feed fresh
  - no active CRITICAL alert / no recent severe deterioration
  - max daily loss, max trades per hour/day, cooldown after a loss
  - growth rate within the profile cap
  - max concurrent open trades
  - live mode requires explicit confirmation
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from ..config import RiskProfile
from ..constants import AlertLevel, Mode, Status
from ..models import DeteriorationResult, MarketScore


@dataclass
class SafeguardLimits:
    max_daily_loss: float = 20.0
    max_trades_per_hour: int = 4
    max_trades_per_day: int = 12
    cooldown_after_loss_sec: float = 300.0
    min_ready_dwell_sec: float = 20.0
    max_concurrent_trades: int = 1
    max_growth_rate: float = 0.03
    min_ready_persistence_ticks: int = 15
    max_deterioration: float = 40.0
    min_data_quality: float = 70.0

    @classmethod
    def from_profile(cls, profile: RiskProfile) -> "SafeguardLimits":
        sg = profile.safeguards or {}
        return cls(
            max_daily_loss=float(sg.get("max_daily_loss", 20.0)),
            max_trades_per_hour=int(sg.get("max_trades_per_hour", 4)),
            max_trades_per_day=int(sg.get("max_trades_per_day", 12)),
            cooldown_after_loss_sec=float(sg.get("cooldown_after_loss_sec", 300.0)),
            min_ready_dwell_sec=float(sg.get("min_ready_dwell_sec", 20.0)),
            max_concurrent_trades=int(sg.get("max_concurrent_trades", 1)),
            max_growth_rate=float(profile.max_growth_rate),
            min_ready_persistence_ticks=int(profile.min_ready_persistence_ticks),
        )


@dataclass
class SafeguardState:
    day_key: str = ""
    daily_pnl: float = 0.0
    trades_today: int = 0
    last_loss_ts: float = -1e9
    open_trades: int = 0
    hourly_ts: deque = field(default_factory=lambda: deque())


class SafeguardDecision:
    def __init__(self, allowed: bool, reasons: list[str]) -> None:
        self.allowed = allowed
        self.reasons = reasons

    def __bool__(self) -> bool:
        return self.allowed

    def __repr__(self) -> str:
        return f"SafeguardDecision(allowed={self.allowed}, reasons={self.reasons})"


class SafeguardEngine:
    def __init__(
        self,
        limits: SafeguardLimits,
        mode: Mode,
        live_confirmed: bool = False,
        clock=time.time,
    ) -> None:
        self.limits = limits
        self.mode = mode
        self.live_confirmed = live_confirmed
        self._clock = clock
        self.state = SafeguardState()

    def _roll_day(self, now: float) -> None:
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        if day != self.state.day_key:
            self.state.day_key = day
            self.state.daily_pnl = 0.0
            self.state.trades_today = 0

    def _trades_last_hour(self, now: float) -> int:
        cutoff = now - 3600
        while self.state.hourly_ts and self.state.hourly_ts[0] < cutoff:
            self.state.hourly_ts.popleft()
        return len(self.state.hourly_ts)

    def can_enter(
        self,
        score: MarketScore,
        deterioration: DeteriorationResult | None,
        active_critical_alert: bool,
        ready_dwell_sec: float,
        proposed_growth_rate: float,
    ) -> SafeguardDecision:
        now = self._clock()
        self._roll_day(now)
        reasons: list[str] = []

        # Readiness.
        if score.status is not Status.READY:
            reasons.append(f"not_ready({score.status.value})")
        if score.ready_persistence < self.limits.min_ready_persistence_ticks:
            reasons.append("readiness_too_brief_ticks")
        if ready_dwell_sec < self.limits.min_ready_dwell_sec:
            reasons.append("readiness_too_brief_time")
        if score.veto_reasons:
            reasons.append("active_veto")

        # Data quality.
        if score.data_quality_score < self.limits.min_data_quality:
            reasons.append("data_quality_low")

        # Alerts / deterioration.
        if active_critical_alert:
            reasons.append("active_critical_alert")
        if deterioration is not None:
            if deterioration.alert_level is AlertLevel.CRITICAL:
                reasons.append("deterioration_critical")
            elif deterioration.deterioration_score > self.limits.max_deterioration:
                reasons.append("deterioration_high")

        # Capital / frequency controls.
        if self.state.daily_pnl <= -abs(self.limits.max_daily_loss):
            reasons.append("max_daily_loss_hit")
        if self.state.trades_today >= self.limits.max_trades_per_day:
            reasons.append("max_trades_per_day")
        if self._trades_last_hour(now) >= self.limits.max_trades_per_hour:
            reasons.append("max_trades_per_hour")
        if now - self.state.last_loss_ts < self.limits.cooldown_after_loss_sec:
            reasons.append("loss_cooldown")
        if self.state.open_trades >= self.limits.max_concurrent_trades:
            reasons.append("max_concurrent_trades")

        # Growth rate cap.
        if proposed_growth_rate > self.limits.max_growth_rate + 1e-9:
            reasons.append("growth_rate_above_cap")

        # Live confirmation (never martingale, never auto-increase stake — those
        # are enforced structurally by the traders, not configurable here).
        if self.mode is Mode.LIVE and not self.live_confirmed:
            reasons.append("live_not_confirmed")

        return SafeguardDecision(len(reasons) == 0, reasons)

    # --- bookkeeping --------------------------------------------------------
    def register_open(self) -> None:
        now = self._clock()
        self._roll_day(now)
        self.state.open_trades += 1
        self.state.trades_today += 1
        self.state.hourly_ts.append(now)

    def register_close(self, pnl: float) -> None:
        now = self._clock()
        self._roll_day(now)
        self.state.open_trades = max(0, self.state.open_trades - 1)
        self.state.daily_pnl += pnl
        if pnl < 0:
            self.state.last_loss_ts = now
