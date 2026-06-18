"""SQLite persistence (stdlib sqlite3).

Persists scores, alerts, trades, rejected trades, risk-limit triggers and daily
summaries for audit and backtest analysis. Designed to be optional: if the DB
URL is ``:memory:`` or disabled, the app still runs (analytics path needs no
storage to function).
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL, symbol TEXT, epoch INTEGER, mqs REAL, status TEXT,
    stability REAL, jump_risk REAL, danger_pct REAL, data_quality REAL,
    suggested_growth_rate REAL, confidence REAL, sub_scores TEXT
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL, symbol TEXT, epoch INTEGER, level TEXT, reason TEXT,
    message TEXT, detail TEXT
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL, symbol TEXT, mode TEXT, entry_epoch INTEGER, exit_epoch INTEGER,
    growth_rate REAL, stake REAL, take_profit REAL, pnl REAL, exit_reason TEXT,
    entry_mqs REAL
);
CREATE TABLE IF NOT EXISTS rejections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL, symbol TEXT, epoch INTEGER, reasons TEXT, mode TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL, event_type TEXT, symbol TEXT, payload TEXT
);
CREATE TABLE IF NOT EXISTS daily_summary (
    day TEXT PRIMARY KEY, payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_scores_symbol ON scores(symbol, epoch);
CREATE INDEX IF NOT EXISTS idx_alerts_symbol ON alerts(symbol, ts);
"""


def _path_from_url(db_url: str) -> str:
    if db_url.startswith("sqlite:///"):
        return db_url[len("sqlite:///"):]
    if db_url.startswith("sqlite://"):
        return db_url[len("sqlite://"):]
    return db_url


class Storage:
    def __init__(self, db_url: str = ":memory:") -> None:
        path = _path_from_url(db_url)
        if path not in (":memory:", ""):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path or ":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # --- writers ------------------------------------------------------------
    def insert_score(self, score: Any) -> None:
        s = score
        self.conn.execute(
            "INSERT INTO scores(ts,symbol,epoch,mqs,status,stability,jump_risk,"
            "danger_pct,data_quality,suggested_growth_rate,confidence,sub_scores)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (time.time(), s.symbol, s.epoch, s.mqs, s.status.value, s.stability_score,
             s.jump_risk_score, s.danger_pct, s.data_quality_score,
             s.suggested_growth_rate, s.confidence, json.dumps(s.sub_scores.__dict__)),
        )
        self.conn.commit()

    def insert_alert(self, alert: Any) -> None:
        self.conn.execute(
            "INSERT INTO alerts(ts,symbol,epoch,level,reason,message,detail)"
            " VALUES(?,?,?,?,?,?,?)",
            (time.time(), alert.symbol, alert.epoch, alert.level.value,
             alert.reason.value, alert.message, json.dumps(alert.detail)),
        )
        self.conn.commit()

    def insert_trade(self, trade: Any) -> None:
        self.conn.execute(
            "INSERT INTO trades(ts,symbol,mode,entry_epoch,exit_epoch,growth_rate,"
            "stake,take_profit,pnl,exit_reason,entry_mqs) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (time.time(), trade.symbol, trade.mode, trade.entry_epoch, trade.exit_epoch,
             trade.growth_rate, trade.stake, trade.take_profit, trade.pnl,
             trade.exit_reason, trade.entry_mqs),
        )
        self.conn.commit()

    def insert_rejection(self, symbol: str, epoch: int, reasons: list[str], mode: str) -> None:
        self.conn.execute(
            "INSERT INTO rejections(ts,symbol,epoch,reasons,mode) VALUES(?,?,?,?,?)",
            (time.time(), symbol, epoch, json.dumps(reasons), mode),
        )
        self.conn.commit()

    def insert_event(self, event_type: str, symbol: str, payload: dict) -> None:
        self.conn.execute(
            "INSERT INTO events(ts,event_type,symbol,payload) VALUES(?,?,?,?)",
            (time.time(), event_type, symbol, json.dumps(payload)),
        )
        self.conn.commit()

    def upsert_daily_summary(self, day: str, payload: dict) -> None:
        self.conn.execute(
            "INSERT INTO daily_summary(day,payload) VALUES(?,?) "
            "ON CONFLICT(day) DO UPDATE SET payload=excluded.payload",
            (day, json.dumps(payload)),
        )
        self.conn.commit()

    # --- readers ------------------------------------------------------------
    def recent_alerts(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def trade_stats(self) -> dict:
        row = self.conn.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(pnl),0) pnl, "
            "COALESCE(SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END),0) wins FROM trades"
        ).fetchone()
        n = row["n"] or 0
        return {
            "trades": n,
            "net_pnl": round(row["pnl"], 2),
            "wins": row["wins"],
            "win_rate": round(row["wins"] / n, 4) if n else 0.0,
        }
