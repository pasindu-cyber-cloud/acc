"""SQLite persistence for ProcAI.

A single :class:`Database` instance is shared by the engine, service and GUI.
SQLite is opened with ``check_same_thread=False`` and guarded by a re-entrant
lock so the background monitor thread and the GUI thread can both use it safely.

All write helpers are small and explicit; there is no ORM. Stored data:

* ``process_history``  -- rolling telemetry, pruned by retention policy
* ``alerts``           -- raised alerts with full reasoning
* ``baselines``        -- Welford running stats per executable+metric
* ``model_metadata``   -- trained ML model descriptors
* ``reputation_list``  -- allow/block entries
* ``labelled_samples`` -- training data for retraining
* ``settings``/``meta``-- key/value bookkeeping
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from importlib import resources
from pathlib import Path
from typing import Any, Iterable, Optional

from ..config import PATHS
from ..core.models import Alert, ModelMetadata, ProcessSnapshot, Severity
from ..utils.logging_setup import get_logger

log = get_logger("data.database")

SCHEMA_VERSION = 1


class Database:
    """Thread-safe SQLite wrapper for ProcAI."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else PATHS.db_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL;")
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._init_schema()

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def _init_schema(self) -> None:
        schema = self._load_schema_sql()
        with self._lock:
            self._conn.executescript(schema)
            self._conn.commit()
            cur = self._conn.execute("SELECT value FROM meta WHERE key = 'schema_version'")
            row = cur.fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
                self._conn.commit()

    @staticmethod
    def _load_schema_sql() -> str:
        # Works both from source tree and from an installed/packaged build.
        try:
            return resources.files("procai.data").joinpath("schema.sql").read_text("utf-8")
        except (FileNotFoundError, ModuleNotFoundError, AttributeError):
            return (Path(__file__).with_name("schema.sql")).read_text("utf-8")

    def close(self) -> None:
        with self._lock:
            self._conn.commit()
            self._conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # Settings (key/value mirror of settings.json)
    # ------------------------------------------------------------------ #
    def set_setting(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_at = excluded.updated_at",
                (key, json.dumps(value), time.time()),
            )
            self._conn.commit()

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock:
            cur = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cur.fetchone()
        return json.loads(row["value"]) if row else default

    # ------------------------------------------------------------------ #
    # Process history
    # ------------------------------------------------------------------ #
    def insert_process_snapshot(
        self, snap: ProcessSnapshot, risk_score: float = 0.0, severity: int = 0
    ) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO process_history
                   (ts, pid, name, exe_path, username, ppid, parent_name,
                    cpu_percent, memory_rss, memory_percent, num_threads,
                    num_handles, num_connections, is_signed, in_suspicious_dir,
                    risk_score, severity)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    snap.timestamp, snap.pid, snap.name, snap.exe_path, snap.username,
                    snap.ppid, snap.parent_name, snap.cpu_percent, snap.memory_rss,
                    snap.memory_percent, snap.num_threads, snap.num_handles,
                    snap.num_connections,
                    None if snap.is_signed is None else int(snap.is_signed),
                    int(snap.in_suspicious_dir), risk_score, severity,
                ),
            )
            self._conn.commit()

    def insert_process_snapshots(
        self, rows: Iterable[tuple[ProcessSnapshot, float, int]]
    ) -> None:
        """Batch insert: iterable of (snapshot, risk_score, severity)."""
        payload = [
            (
                s.timestamp, s.pid, s.name, s.exe_path, s.username, s.ppid, s.parent_name,
                s.cpu_percent, s.memory_rss, s.memory_percent, s.num_threads, s.num_handles,
                s.num_connections, None if s.is_signed is None else int(s.is_signed),
                int(s.in_suspicious_dir), score, sev,
            )
            for (s, score, sev) in rows
        ]
        if not payload:
            return
        with self._lock:
            self._conn.executemany(
                """INSERT INTO process_history
                   (ts, pid, name, exe_path, username, ppid, parent_name,
                    cpu_percent, memory_rss, memory_percent, num_threads,
                    num_handles, num_connections, is_signed, in_suspicious_dir,
                    risk_score, severity)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                payload,
            )
            self._conn.commit()

    def recent_process_history(self, pid: Optional[int] = None, limit: int = 200) -> list[dict]:
        with self._lock:
            if pid is None:
                cur = self._conn.execute(
                    "SELECT * FROM process_history ORDER BY ts DESC LIMIT ?", (limit,)
                )
            else:
                cur = self._conn.execute(
                    "SELECT * FROM process_history WHERE pid = ? ORDER BY ts DESC LIMIT ?",
                    (pid, limit),
                )
            return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------ #
    # Alerts
    # ------------------------------------------------------------------ #
    def insert_alert(self, alert: Alert) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO alerts
                   (ts, pid, process_name, exe_path, username, risk_score, severity,
                    confidence, reasons_json, rule_hits_json, ml_probability,
                    recommended_action, acknowledged, resolution)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    alert.timestamp, alert.pid, alert.process_name, alert.exe_path,
                    alert.username, alert.risk_score, int(alert.severity), alert.confidence,
                    json.dumps(alert.reasons), json.dumps(alert.rule_hits),
                    alert.ml_probability, alert.recommended_action,
                    int(alert.acknowledged), alert.resolution,
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def get_alerts(
        self,
        *,
        limit: int = 200,
        min_severity: Optional[Severity] = None,
        unacknowledged_only: bool = False,
        since: Optional[float] = None,
    ) -> list[Alert]:
        query = "SELECT * FROM alerts WHERE 1=1"
        params: list[Any] = []
        if min_severity is not None:
            query += " AND severity >= ?"
            params.append(int(min_severity))
        if unacknowledged_only:
            query += " AND acknowledged = 0"
        if since is not None:
            query += " AND ts >= ?"
            params.append(since)
        query += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            cur = self._conn.execute(query, params)
            return [self._row_to_alert(r) for r in cur.fetchall()]

    def acknowledge_alert(self, alert_id: int, resolution: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE alerts SET acknowledged = 1, resolution = ? WHERE id = ?",
                (resolution, alert_id),
            )
            self._conn.commit()

    def alert_counts_by_severity(self, since: Optional[float] = None) -> dict[int, int]:
        query = "SELECT severity, COUNT(*) c FROM alerts"
        params: list[Any] = []
        if since is not None:
            query += " WHERE ts >= ?"
            params.append(since)
        query += " GROUP BY severity"
        with self._lock:
            cur = self._conn.execute(query, params)
            return {int(r["severity"]): int(r["c"]) for r in cur.fetchall()}

    @staticmethod
    def _row_to_alert(r: sqlite3.Row) -> Alert:
        return Alert(
            id=r["id"],
            timestamp=r["ts"],
            pid=r["pid"],
            process_name=r["process_name"],
            exe_path=r["exe_path"] or "",
            username=r["username"] or "",
            risk_score=r["risk_score"],
            severity=Severity(int(r["severity"])),
            confidence=r["confidence"],
            reasons=json.loads(r["reasons_json"] or "[]"),
            rule_hits=json.loads(r["rule_hits_json"] or "[]"),
            ml_probability=r["ml_probability"] or 0.0,
            recommended_action=r["recommended_action"] or "",
            acknowledged=bool(r["acknowledged"]),
            resolution=r["resolution"] or "",
        )

    # ------------------------------------------------------------------ #
    # Baselines (Welford running statistics)
    # ------------------------------------------------------------------ #
    def get_baseline(self, identity_key: str, metric: str) -> Optional[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM baselines WHERE identity_key = ? AND metric = ?",
                (identity_key, metric),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def upsert_baseline(
        self,
        identity_key: str,
        metric: str,
        count: int,
        mean: float,
        m2: float,
        min_value: float,
        max_value: float,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO baselines
                   (identity_key, metric, count, mean, m2, min_value, max_value, updated_at)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(identity_key, metric) DO UPDATE SET
                     count=excluded.count, mean=excluded.mean, m2=excluded.m2,
                     min_value=excluded.min_value, max_value=excluded.max_value,
                     updated_at=excluded.updated_at""",
                (identity_key, metric, count, mean, m2, min_value, max_value, time.time()),
            )
            self._conn.commit()

    def baseline_identity_count(self) -> int:
        with self._lock:
            cur = self._conn.execute(
                "SELECT COUNT(DISTINCT identity_key) c FROM baselines"
            )
            return int(cur.fetchone()["c"])

    # ------------------------------------------------------------------ #
    # Model metadata
    # ------------------------------------------------------------------ #
    def upsert_model_metadata(self, md: ModelMetadata) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO model_metadata
                   (name, algorithm, trained_at, n_samples, n_features,
                    feature_names_json, accuracy, precision_, recall, f1, notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(name) DO UPDATE SET
                     algorithm=excluded.algorithm, trained_at=excluded.trained_at,
                     n_samples=excluded.n_samples, n_features=excluded.n_features,
                     feature_names_json=excluded.feature_names_json,
                     accuracy=excluded.accuracy, precision_=excluded.precision_,
                     recall=excluded.recall, f1=excluded.f1, notes=excluded.notes""",
                (
                    md.name, md.algorithm, md.trained_at, md.n_samples, md.n_features,
                    json.dumps(md.feature_names), md.accuracy, md.precision, md.recall,
                    md.f1, md.notes,
                ),
            )
            self._conn.commit()

    def get_model_metadata(self, name: str) -> Optional[ModelMetadata]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM model_metadata WHERE name = ?", (name,))
            r = cur.fetchone()
        if not r:
            return None
        return ModelMetadata(
            name=r["name"], algorithm=r["algorithm"], trained_at=r["trained_at"],
            n_samples=r["n_samples"], n_features=r["n_features"],
            feature_names=json.loads(r["feature_names_json"]),
            accuracy=r["accuracy"] or 0.0, precision=r["precision_"] or 0.0,
            recall=r["recall"] or 0.0, f1=r["f1"] or 0.0, notes=r["notes"] or "",
        )

    # ------------------------------------------------------------------ #
    # Reputation list (allow/block)
    # ------------------------------------------------------------------ #
    def add_reputation(self, list_type: str, pattern: str, note: str = "") -> None:
        assert list_type in ("allow", "block")
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO reputation_list (list_type, pattern, note, created_at) "
                "VALUES (?,?,?,?)",
                (list_type, pattern.lower(), note, time.time()),
            )
            self._conn.commit()

    def remove_reputation(self, list_type: str, pattern: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM reputation_list WHERE list_type = ? AND pattern = ?",
                (list_type, pattern.lower()),
            )
            self._conn.commit()

    def get_reputation(self, list_type: str) -> list[str]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT pattern FROM reputation_list WHERE list_type = ?", (list_type,)
            )
            return [r["pattern"] for r in cur.fetchall()]

    # ------------------------------------------------------------------ #
    # Labelled samples (for ML retraining)
    # ------------------------------------------------------------------ #
    def add_labelled_sample(
        self, features: dict[str, float], label: int, source: str = "user"
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO labelled_samples (ts, features_json, label, source) "
                "VALUES (?,?,?,?)",
                (time.time(), json.dumps(features), int(label), source),
            )
            self._conn.commit()

    def get_labelled_samples(self) -> list[tuple[dict[str, float], int]]:
        with self._lock:
            cur = self._conn.execute("SELECT features_json, label FROM labelled_samples")
            return [(json.loads(r["features_json"]), int(r["label"])) for r in cur.fetchall()]

    def labelled_sample_count(self) -> int:
        with self._lock:
            cur = self._conn.execute("SELECT COUNT(*) c FROM labelled_samples")
            return int(cur.fetchone()["c"])

    # ------------------------------------------------------------------ #
    # Retention / maintenance
    # ------------------------------------------------------------------ #
    def prune_retention(
        self, process_history_days: int, alert_days: Optional[int] = None
    ) -> dict[str, int]:
        """Delete rows older than the retention windows. Returns deletion counts."""
        now = time.time()
        deleted: dict[str, int] = {}
        with self._lock:
            cutoff = now - process_history_days * 86400
            cur = self._conn.execute("DELETE FROM process_history WHERE ts < ?", (cutoff,))
            deleted["process_history"] = cur.rowcount
            if alert_days is not None:
                acut = now - alert_days * 86400
                cur = self._conn.execute(
                    "DELETE FROM alerts WHERE ts < ? AND acknowledged = 1", (acut,)
                )
                deleted["alerts"] = cur.rowcount
            self._conn.commit()
        log.info("Retention prune removed: %s", deleted)
        return deleted

    def vacuum(self) -> None:
        with self._lock:
            self._conn.execute("VACUUM")
