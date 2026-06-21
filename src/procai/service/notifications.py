"""Desktop notifications for alerts.

The notifier is backend-agnostic. The preferred backend is the system-tray icon
(pystray balloon notifications); when the GUI/tray is running it registers its
``notify`` function here. If no graphical backend is available the notifier
falls back to a Windows toast via PowerShell, and finally to the log file. This
keeps notifications working in headless service mode without hard dependencies.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from typing import Callable, Optional

from ..config import Settings
from ..core.models import Alert, Severity
from ..utils.logging_setup import get_logger

log = get_logger("service.notifications")

NotifyBackend = Callable[[str, str], None]


class Notifier:
    """Routes alert notifications to the best available backend."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._backend: Optional[NotifyBackend] = None
        self._lock = threading.Lock()

    def set_backend(self, backend: Optional[NotifyBackend]) -> None:
        with self._lock:
            self._backend = backend

    # ------------------------------------------------------------------ #
    def should_notify(self, alert: Alert) -> bool:
        if not self.settings.desktop_notifications:
            return False
        min_sev = Severity.from_name(self.settings.notify_min_severity)
        return alert.severity >= min_sev

    def notify_alert(self, alert: Alert) -> None:
        if not self.should_notify(alert):
            return
        title = f"ProcAI - {alert.severity.label} risk: {alert.process_name}"
        body = (
            f"PID {alert.pid} scored {alert.risk_score:.0f}/100.\n"
            f"{alert.recommended_action}"
        )
        self.notify(title, body)

    def notify(self, title: str, message: str) -> None:
        with self._lock:
            backend = self._backend
        if backend is not None:
            try:
                backend(title, message)
                return
            except Exception as exc:  # pragma: no cover
                log.debug("Primary notify backend failed: %s", exc)
        self._fallback(title, message)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _fallback(title: str, message: str) -> None:
        if sys.platform.startswith("win"):
            try:
                # Lightweight balloon via Windows Script Host; read-only, no installs.
                safe_t = title.replace("'", "")
                safe_m = message.replace("'", "").replace("\n", " ")
                ps = (
                    "[reflection.assembly]::loadwithpartialname('System.Windows.Forms')"
                    " | Out-Null;"
                    "$n=New-Object System.Windows.Forms.NotifyIcon;"
                    "$n.Icon=[System.Drawing.SystemIcons]::Information;"
                    "$n.BalloonTipTitle='" + safe_t + "';"
                    "$n.BalloonTipText='" + safe_m + "';"
                    "$n.Visible=$true;$n.ShowBalloonTip(8000);Start-Sleep -s 9;$n.Dispose()"
                )
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps]
                )
                return
            except Exception as exc:  # pragma: no cover
                log.debug("PowerShell toast failed: %s", exc)
        log.info("NOTIFY: %s - %s", title, message)
