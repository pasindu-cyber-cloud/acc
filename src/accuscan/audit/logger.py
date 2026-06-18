"""Structured audit logging.

Every meaningful event is written as a single JSON line (timestamp, symbol,
event type, score, sub-scores, reason, action, mode, latency/quality metadata)
to an append-only log file, mirrored to an in-memory ring buffer for the
dashboard, and optionally persisted to SQLite.

Persisted: all score changes, alerts, proposals, entries/exits, rejected
trades, risk-limit triggers and daily summaries.
"""

from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path
from typing import Any

from ..models import Alert, DeteriorationResult, MarketScore, TradeRecord, asdict_json


class AuditLogger:
    def __init__(
        self,
        log_path: str | None = "storage/accuscan.audit.jsonl",
        storage: Any = None,
        buffer_size: int = 1000,
        mode: str = "analytics",
    ) -> None:
        self.mode = mode
        self.storage = storage
        self._buffer: deque[dict] = deque(maxlen=buffer_size)
        self._fh = None
        if log_path:
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(log_path, "a", encoding="utf-8")  # noqa: SIM115

    def _write(self, record: dict) -> None:
        record.setdefault("ts", time.time())
        record.setdefault("mode", self.mode)
        self._buffer.append(record)
        if self._fh:
            self._fh.write(json.dumps(record, default=str) + "\n")
            self._fh.flush()

    def recent(self, n: int = 100) -> list[dict]:
        return list(self._buffer)[-n:]

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None

    # --- typed events -------------------------------------------------------
    def log_score(self, score: MarketScore) -> None:
        self._write({
            "event": "score",
            "symbol": score.symbol,
            "epoch": score.epoch,
            "mqs": score.mqs,
            "status": score.status.value,
            "sub_scores": asdict_json(score.sub_scores),
            "stability": score.stability_score,
            "jump_risk": score.jump_risk_score,
            "danger_pct": score.danger_pct,
            "data_quality": score.data_quality_score,
            "suggested_growth_rate": score.suggested_growth_rate,
            "confidence": score.confidence,
            "veto": score.veto_reasons,
        })
        if self.storage:
            self.storage.insert_score(score)

    def log_alert(self, alert: Alert) -> None:
        self._write({
            "event": "alert",
            "symbol": alert.symbol,
            "epoch": alert.epoch,
            "level": alert.level.value,
            "reason": alert.reason.value,
            "message": alert.message,
            "detail": alert.detail,
        })
        if self.storage:
            self.storage.insert_alert(alert)

    def log_deterioration(self, result: DeteriorationResult) -> None:
        self._write({
            "event": "deterioration",
            "symbol": result.symbol,
            "epoch": result.epoch,
            "deterioration": result.deterioration_score,
            "health": result.health_label.value,
            "alert_level": result.alert_level.value,
            "action": result.recommended_action,
            "reasons": result.reasons,
            "cusum": result.cusum,
            "zscore": result.zscore,
            "score_drop": result.score_drop,
        })

    def log_trade(self, trade: TradeRecord, event: str = "trade_close") -> None:
        self._write({
            "event": event,
            "symbol": trade.symbol,
            "mode": trade.mode,
            "entry_epoch": trade.entry_epoch,
            "exit_epoch": trade.exit_epoch,
            "growth_rate": trade.growth_rate,
            "stake": trade.stake,
            "take_profit": trade.take_profit,
            "pnl": trade.pnl,
            "exit_reason": trade.exit_reason,
            "entry_mqs": trade.entry_mqs,
        })
        if self.storage:
            self.storage.insert_trade(trade)

    def log_rejection(self, symbol: str, epoch: int, reasons: list[str]) -> None:
        self._write({
            "event": "trade_rejected",
            "symbol": symbol,
            "epoch": epoch,
            "reasons": reasons,
        })
        if self.storage:
            self.storage.insert_rejection(symbol, epoch, reasons, self.mode)

    def log_proposal(self, symbol: str, growth_rate: float, stake: float, take_profit: float | None) -> None:
        self._write({
            "event": "proposal",
            "symbol": symbol,
            "growth_rate": growth_rate,
            "stake": stake,
            "take_profit": take_profit,
        })

    def daily_summary(self, day: str, payload: dict) -> None:
        self._write({"event": "daily_summary", "day": day, **payload})
        if self.storage:
            self.storage.upsert_daily_summary(day, payload)
