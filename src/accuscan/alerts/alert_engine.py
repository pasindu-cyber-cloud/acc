"""Alert Engine.

Converts scoring vetoes and deterioration results into INFO/WARNING/CRITICAL
alerts, with per-(symbol, reason) throttling so a persistent condition does not
spam. Alerts are buffered for the dashboard and forwarded to any registered
sink callbacks (console, websocket push, audit log, ...).
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

from ..constants import AlertLevel, AlertReason
from ..models import Alert, DeteriorationResult, MarketScore

# Map free-text reason strings (from scoring/deterioration) to AlertReason.
_REASON_MAP = {
    "jump_burst": AlertReason.JUMP_BURST,
    "jump_burst_probability": AlertReason.JUMP_BURST,
    "short_window_tail_jump": AlertReason.JUMP_BURST,
    "volatility_expansion": AlertReason.VOLATILITY_EXPANSION,
    "vol_zscore": AlertReason.VOLATILITY_EXPANSION,
    "cusum_shift": AlertReason.VOLATILITY_EXPANSION,
    "danger_digit_burst_25": AlertReason.DANGER_DIGIT_CLUSTER,
    "danger_digit_cluster_100": AlertReason.DANGER_DIGIT_CLUSTER,
    "danger_digit_increase": AlertReason.DANGER_DIGIT_CLUSTER,
    "short_window_degradation": AlertReason.SHORT_WINDOW_DEGRADATION,
    "score_drop": AlertReason.SCORE_COLLAPSE,
    "trend_reversal": AlertReason.TREND_REVERSAL,
    "data_staleness": AlertReason.DATA_STALENESS,
    "data_quality": AlertReason.DATA_STALENESS,
    "latency": AlertReason.LATENCY,
    "contract_health": AlertReason.CONTRACT_HEALTH,
    "readiness_too_brief": AlertReason.READINESS_TOO_BRIEF,
}


class AlertEngine:
    def __init__(self, throttle_sec: float = 5.0, buffer_size: int = 500) -> None:
        self.throttle_sec = throttle_sec
        self._last_emit: dict[tuple[str, str], float] = {}
        self._buffer: deque[Alert] = deque(maxlen=buffer_size)
        self._sinks: list[Callable[[Alert], None]] = []

    def add_sink(self, sink: Callable[[Alert], None]) -> None:
        self._sinks.append(sink)

    def recent(self, n: int = 50) -> list[Alert]:
        return list(self._buffer)[-n:]

    def _emit(self, alert: Alert, now: float | None = None) -> bool:
        now = now if now is not None else time.monotonic()
        key = (alert.symbol, f"{alert.level.value}:{alert.reason.value}")
        last = self._last_emit.get(key, -1e9)
        if now - last < self.throttle_sec:
            return False
        self._last_emit[key] = now
        self._buffer.append(alert)
        for sink in self._sinks:
            try:
                sink(alert)
            except Exception:
                # A misbehaving sink must never break the pipeline.
                pass
        return True

    # --- builders -----------------------------------------------------------
    def from_score(self, score: MarketScore, now: float | None = None) -> list[Alert]:
        out: list[Alert] = []
        for reason_str in score.veto_reasons:
            reason = _REASON_MAP.get(reason_str, AlertReason.SCORE_COLLAPSE)
            level = AlertLevel.CRITICAL if reason in (
                AlertReason.JUMP_BURST, AlertReason.DATA_STALENESS
            ) else AlertLevel.WARNING
            alert = Alert(
                symbol=score.symbol, epoch=score.epoch, level=level, reason=reason,
                message=f"{score.symbol}: veto '{reason_str}' (MQS {score.mqs:.1f})",
                detail={"mqs": score.mqs, "veto": reason_str, "status": score.status.value},
            )
            if self._emit(alert, now):
                out.append(alert)
        return out

    def from_deterioration(
        self, result: DeteriorationResult, now: float | None = None
    ) -> list[Alert]:
        if result.alert_level is AlertLevel.INFO and not result.reasons:
            return []
        out: list[Alert] = []
        # Emit one alert per distinct reason at the overall alert level.
        reasons = result.reasons or ["score_drop"]
        for reason_str in reasons:
            reason = _REASON_MAP.get(reason_str, AlertReason.SCORE_COLLAPSE)
            alert = Alert(
                symbol=result.symbol,
                epoch=result.epoch,
                level=result.alert_level,
                reason=reason,
                message=(
                    f"{result.symbol}: {result.health_label.value} "
                    f"(deterioration {result.deterioration_score:.0f}) -> "
                    f"{result.recommended_action}"
                ),
                detail={
                    "deterioration": result.deterioration_score,
                    "reason": reason_str,
                    "score_drop": result.score_drop,
                    "cusum": result.cusum,
                    "zscore": result.zscore,
                    "action": result.recommended_action,
                },
            )
            if self._emit(alert, now):
                out.append(alert)
        return out
