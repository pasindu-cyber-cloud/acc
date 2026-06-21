"""Headless background service runner.

This is the visible, transparent background component referenced by the
installer/Task Scheduler. It runs the monitoring loop without the GUI, routes
alerts to desktop notifications, and shuts down cleanly on Ctrl-C / SIGTERM.

It is deliberately a normal user-space process (or a user Scheduled Task), not a
hidden system service that conceals itself. The user can stop it at any time
from the tray, the dashboard, or the OS task manager.
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
import time
from typing import Optional

from ..config import PATHS, Settings
from ..core.engine import ProcAIEngine
from ..core.models import Alert, DetectionResult
from ..core.monitor import Monitor
from ..utils import audit
from ..utils.logging_setup import configure, get_logger
from .notifications import Notifier

log = get_logger("service.background")

# Cross-process stop signal: the uninstaller / `procai --stop` writes this file,
# and a running service polls for it and shuts down cleanly. This avoids killing
# unrelated processes and keeps shutdown transparent and cooperative.
STOP_FLAG = PATHS.data_dir / "service.stop"


def request_stop() -> None:
    """Signal any running ProcAI service to stop (cooperative, cross-process)."""
    try:
        PATHS.ensure()
        STOP_FLAG.write_text(str(time.time()), encoding="utf-8")
        log.info("Wrote service stop flag: %s", STOP_FLAG)
    except OSError as exc:  # pragma: no cover
        log.warning("Could not write stop flag: %s", exc)


class BackgroundService:
    """Owns an engine + monitor + notifier for headless operation."""

    def __init__(self, settings: Optional[Settings] = None, *, with_tray: bool = False) -> None:
        self.settings = settings or Settings.load()
        self.engine = ProcAIEngine(settings=self.settings)
        self.monitor = Monitor(self.engine)
        self.notifier = Notifier(self.settings)
        self._stop_event = threading.Event()
        self._tray = None

        self.engine.add_alert_callback(self._on_alert)

        if with_tray:
            self._init_tray()

    # ------------------------------------------------------------------ #
    def _init_tray(self) -> None:
        from .tray import SystemTray, tray_available

        if not tray_available():
            log.info("Tray requested but pystray is unavailable; continuing headless.")
            return
        self._tray = SystemTray(self.monitor, on_quit=self.shutdown)
        # Route notifications through the tray balloon.
        self.notifier.set_backend(self._tray.notify)
        self._tray.run_detached()

    # ------------------------------------------------------------------ #
    def _on_alert(self, alert: Alert, _result: DetectionResult) -> None:
        self.notifier.notify_alert(alert)

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        # Clear any stale stop flag from a previous run.
        try:
            if STOP_FLAG.exists():
                STOP_FLAG.unlink()
        except OSError:
            pass
        audit.record("service.start", {"with_tray": self._tray is not None}, actor="service")
        self.monitor.start()
        log.info("ProcAI background service started.")

    def shutdown(self, *_args) -> None:
        if self._stop_event.is_set():
            return
        log.info("Shutting down ProcAI background service...")
        self._stop_event.set()
        self.monitor.stop()
        if self._tray is not None:
            self._tray.stop()
        self.engine.close()
        audit.record("service.stop", {}, actor="service")

    def run_forever(self) -> None:
        self.start()
        try:
            while not self._stop_event.is_set():
                time.sleep(0.5)
                if STOP_FLAG.exists():
                    log.info("Stop flag detected; shutting down service.")
                    try:
                        STOP_FLAG.unlink()
                    except OSError:
                        pass
                    break
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()


def _install_signal_handlers(service: BackgroundService) -> None:
    for sig in (signal.SIGINT, getattr(signal, "SIGTERM", signal.SIGINT)):
        try:
            signal.signal(sig, service.shutdown)
        except (ValueError, OSError):  # pragma: no cover - non-main thread
            pass


def run_service_cli(argv: Optional[list[str]] = None) -> int:
    """Entry point for the ``procai-service`` console script."""
    import argparse

    parser = argparse.ArgumentParser(description="ProcAI background monitoring service.")
    parser.add_argument("--tray", action="store_true", help="Show a system-tray icon.")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging to console.")
    args = parser.parse_args(argv)

    configure(level=logging.DEBUG if args.verbose else logging.INFO, console=True)
    service = BackgroundService(with_tray=args.tray)
    _install_signal_handlers(service)
    service.run_forever()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run_service_cli())
