"""Background monitoring loop.

A :class:`Monitor` repeatedly drives :meth:`ProcAIEngine.scan_once` on a timer in
a dedicated daemon thread. It is fully controllable -- ``start``/``stop``/``pause``
-- and exposes the latest results so the GUI can render without re-scanning.

This is ordinary, visible, user-controlled background work: it is not a hidden
process, it is stoppable at any time, and it only reads data the OS already
exposes.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from .engine import ProcAIEngine
from .models import DetectionResult
from ..utils import audit
from ..utils.logging_setup import get_logger

log = get_logger("core.monitor")

ScanCallback = Callable[[list[DetectionResult]], None]


class Monitor:
    """Drives periodic scans on a daemon thread."""

    def __init__(self, engine: ProcAIEngine) -> None:
        self.engine = engine
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._scan_callbacks: list[ScanCallback] = []
        self._last_results: list[DetectionResult] = []
        self._last_scan_at: float = 0.0
        self._scan_count: int = 0
        self._lock = threading.RLock()
        self._retention_interval_s = 3600.0
        self._last_retention = 0.0

    # ------------------------------------------------------------------ #
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop.is_set()

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    @property
    def last_results(self) -> list[DetectionResult]:
        with self._lock:
            return list(self._last_results)

    @property
    def stats(self) -> dict[str, float]:
        return {
            "running": self.running,
            "paused": self.paused,
            "scan_count": self._scan_count,
            "last_scan_at": self._last_scan_at,
            "tracked_processes": len(self._last_results),
        }

    # ------------------------------------------------------------------ #
    def add_scan_callback(self, cb: ScanCallback) -> None:
        self._scan_callbacks.append(cb)

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._paused.clear()
        self.engine.collector.prime()  # warm CPU counters before first real scan
        self._thread = threading.Thread(target=self._loop, name="procai-monitor", daemon=True)
        self._thread.start()
        audit.record("monitoring.start", {"interval_s": self.engine.settings.scan_interval_seconds},
                     actor="service")
        log.info("Monitor started.")

    def stop(self, timeout: float = 5.0) -> None:
        if not self._thread:
            return
        self._stop.set()
        self._thread.join(timeout=timeout)
        self._thread = None
        audit.record("monitoring.stop", {}, actor="service")
        log.info("Monitor stopped.")

    def pause(self) -> None:
        self._paused.set()
        audit.record("monitoring.pause", {}, actor="user")

    def resume(self) -> None:
        self._paused.clear()
        audit.record("monitoring.resume", {}, actor="user")

    # ------------------------------------------------------------------ #
    def _loop(self) -> None:
        while not self._stop.is_set():
            interval = max(0.5, float(self.engine.settings.scan_interval_seconds))
            if not self._paused.is_set():
                try:
                    self._do_scan()
                except Exception as exc:  # a scan error must never kill the loop
                    log.exception("Scan failed: %s", exc)
            # Sleep in small slices so stop() is responsive.
            waited = 0.0
            while waited < interval and not self._stop.is_set():
                time.sleep(min(0.25, interval - waited))
                waited += 0.25

    def _do_scan(self) -> None:
        results = self.engine.scan_once()
        with self._lock:
            self._last_results = results
            self._last_scan_at = time.time()
            self._scan_count += 1
        for cb in list(self._scan_callbacks):
            try:
                cb(results)
            except Exception as exc:  # pragma: no cover
                log.debug("Scan callback failed: %s", exc)
        # Periodic retention housekeeping.
        now = time.time()
        if now - self._last_retention > self._retention_interval_s:
            self._last_retention = now
            try:
                self.engine.run_retention()
            except Exception as exc:  # pragma: no cover
                log.debug("Retention failed: %s", exc)
