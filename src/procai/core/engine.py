"""ProcAIEngine: the single orchestration facade.

Both the GUI and the background service talk to this one object instead of
wiring the individual components together themselves. It owns:

* the :class:`Database`,
* the live :class:`Settings`,
* the :class:`TelemetryCollector`, :class:`BaselineManager`,
  :class:`RuleEngine`, :class:`MLClassifier` and :class:`HybridEngine`,
* learning-mode state.

A single ``scan_once`` call performs the full pipeline for the whole process
table and returns the per-process :class:`DetectionResult` list, persisting
history, updating baselines, and raising/deduplicating alerts.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from .baseline import BaselineManager, LearningMode
from .hybrid import HybridConfig, HybridEngine
from .ml import MLClassifier, ml_available
from .models import Alert, DetectionResult, ProcessSnapshot
from .reputation import enrich
from .rules import RuleEngine
from .telemetry import TelemetryCollector, system_overview
from ..config import PATHS, Settings
from ..data.database import Database
from ..utils import audit
from ..utils.logging_setup import get_logger

log = get_logger("core.engine")

# Type for alert callbacks (e.g. desktop notification / GUI refresh).
AlertCallback = Callable[[Alert, DetectionResult], None]


class ProcAIEngine:
    """High-level facade tying telemetry -> detection -> persistence together."""

    def __init__(self, settings: Optional[Settings] = None, db: Optional[Database] = None) -> None:
        PATHS.ensure()
        self.settings = settings or Settings.load()
        self.db = db or Database()
        self._mirror_settings_to_db()

        self.collector = TelemetryCollector(collect_connections=True)
        self.baseline = BaselineManager(self.db, min_samples=self.settings.baseline_min_samples)
        self.rules = RuleEngine()
        self.learning = LearningMode(self.db)

        self.classifier: Optional[MLClassifier] = None
        if self.settings.enable_ml and ml_available():
            clf = MLClassifier(self.settings.preferred_model)
            if clf.load():
                self.classifier = clf

        self.hybrid = HybridEngine(self.rules, self.baseline, self.classifier)

        # Alert de-duplication: remember when we last alerted per identity.
        self._last_alert_at: dict[str, float] = {}
        self._alert_cooldown_s = 120.0
        self._alert_callbacks: list[AlertCallback] = []
        self._lock = threading.RLock()

        # Optionally begin learning mode on first ever run.
        if self.settings.learning_mode and self.learning.remaining_seconds() == 0 and (
            self.db.get_setting("learning_started_at") is None
        ):
            self.learning.start(self.settings.learning_duration_minutes)

    # ------------------------------------------------------------------ #
    # Settings
    # ------------------------------------------------------------------ #
    def _mirror_settings_to_db(self) -> None:
        try:
            self.db.set_setting("settings_json", self.settings.to_dict())
        except Exception:  # pragma: no cover
            pass

    def update_settings(self, new_settings: Settings) -> None:
        with self._lock:
            old = self.settings
            self.settings = new_settings
            new_settings.save()
            self._mirror_settings_to_db()
            self.baseline.min_samples = new_settings.baseline_min_samples
            # Reload model if ML toggled or model choice changed.
            if new_settings.enable_ml and ml_available():
                if (
                    self.classifier is None
                    or self.classifier.name != new_settings.preferred_model
                ):
                    clf = MLClassifier(new_settings.preferred_model)
                    self.classifier = clf if clf.load() else None
                    self.hybrid.classifier = self.classifier
            else:
                self.classifier = None
                self.hybrid.classifier = None
            audit.record(
                "settings.update",
                {
                    "sensitivity": new_settings.sensitivity.value,
                    "enable_ml": new_settings.enable_ml,
                    "ai_assistant_enabled": new_settings.ai_assistant_enabled,
                    "from_sensitivity": old.sensitivity.value,
                },
            )

    # ------------------------------------------------------------------ #
    # Callbacks
    # ------------------------------------------------------------------ #
    def add_alert_callback(self, cb: AlertCallback) -> None:
        self._alert_callbacks.append(cb)

    # ------------------------------------------------------------------ #
    # Scanning
    # ------------------------------------------------------------------ #
    def _config(self) -> HybridConfig:
        return HybridConfig.from_settings(
            self.settings,
            learning_mode=self.settings.learning_mode and self.learning.is_active(),
            extra_allow=self.db.get_reputation("allow"),
            extra_block=self.db.get_reputation("block"),
        )

    def scan_once(
        self,
        snapshots: Optional[list[ProcessSnapshot]] = None,
        *,
        enrich_reputation: bool = True,
        persist: bool = True,
    ) -> list[DetectionResult]:
        """Run the full pipeline once over the given (or live) snapshots."""
        if snapshots is None:
            snapshots = self.collector.collect()
        config = self._config()
        results: list[DetectionResult] = []
        history_rows: list[tuple[ProcessSnapshot, float, int]] = []

        for snap in snapshots:
            if enrich_reputation and snap.exe_path and snap.pid > 0:
                try:
                    enrich(snap, check_signature=True)
                except Exception:  # never let enrichment crash a scan
                    pass
            result = self.hybrid.evaluate(snap, config)
            results.append(result)

            # Update baseline with observed behaviour (the model of "normal").
            self.baseline.update(snap, persist=False)
            history_rows.append((snap, result.risk_score, int(result.severity)))

            if result.should_alert:
                self._raise_alert(result)

        # Persist batched history + baseline.
        if persist:
            try:
                self.db.insert_process_snapshots(history_rows)
            except Exception as exc:  # pragma: no cover
                log.warning("Failed to persist process history: %s", exc)
        # Persist touched baselines.
        for identity in {s.identity_key() for s in snapshots if s.identity_key()}:
            try:
                self.baseline._persist(identity, self.baseline._cache[identity])
            except KeyError:
                continue
        return results

    # ------------------------------------------------------------------ #
    def _raise_alert(self, result: DetectionResult) -> None:
        identity = result.snapshot.identity_key()
        now = time.time()
        last = self._last_alert_at.get(identity, 0.0)
        if now - last < self._alert_cooldown_s:
            return  # de-duplicate alert storms for the same executable
        self._last_alert_at[identity] = now

        alert = Alert.from_detection(result)
        try:
            alert.id = self.db.insert_alert(alert)
        except Exception as exc:  # pragma: no cover
            log.warning("Failed to persist alert: %s", exc)
        audit.record(
            "alert.raise",
            {"pid": alert.pid, "name": alert.process_name, "severity": alert.severity.label,
             "risk": alert.risk_score},
            actor="service",
        )
        for cb in list(self._alert_callbacks):
            try:
                cb(alert, result)
            except Exception as exc:  # pragma: no cover
                log.debug("Alert callback failed: %s", exc)

    # ------------------------------------------------------------------ #
    # Deep scan / single process inspection
    # ------------------------------------------------------------------ #
    def inspect(self, pid: int) -> Optional[DetectionResult]:
        snap = self.collector.collect_one(pid)
        if snap is None:
            return None
        enrich(snap, check_signature=True)
        return self.hybrid.evaluate(snap, self._config())

    # ------------------------------------------------------------------ #
    # Maintenance
    # ------------------------------------------------------------------ #
    def run_retention(self) -> dict[str, int]:
        return self.db.prune_retention(
            self.settings.process_history_retention_days,
            self.settings.log_retention_days,
        )

    def system_overview(self) -> dict[str, float]:
        return system_overview()

    def health(self) -> dict[str, object]:
        """Protection-health snapshot for the GUI's health page."""
        return {
            "monitoring_capable": self.collector is not None,
            "psutil_available": __import__("procai.core.telemetry", fromlist=["psutil_available"]).psutil_available(),
            "ml_available": ml_available(),
            "model_loaded": self.classifier is not None and self.classifier.is_loaded(),
            "model_name": self.classifier.name if self.classifier else "",
            "baseline_identities": self.db.baseline_identity_count(),
            "learning_active": self.learning.is_active(),
            "learning_remaining_min": round(self.learning.remaining_seconds() / 60.0, 1),
            "sensitivity": self.settings.sensitivity.value,
            "privacy_first": self.settings.privacy_first_mode,
            "ai_assistant_enabled": self.settings.ai_assistant_enabled,
            "audit_ok": audit.verify()[0],
        }

    def close(self) -> None:
        self.db.close()
