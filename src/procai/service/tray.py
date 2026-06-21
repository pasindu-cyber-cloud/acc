"""System-tray integration (pystray).

Provides an always-visible tray icon with a menu to open the dashboard, pause or
resume monitoring, view quick status and quit. pystray/Pillow are imported
lazily so headless/core-only environments are unaffected.

The tray is intentionally prominent: ProcAI never hides from the user.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from ..core.monitor import Monitor
from ..utils.logging_setup import get_logger

log = get_logger("service.tray")

try:  # pragma: no cover - only where the gui extra is installed
    import pystray
    from PIL import Image, ImageDraw

    _HAVE_TRAY = True
except Exception:  # pragma: no cover
    _HAVE_TRAY = False


def tray_available() -> bool:
    return _HAVE_TRAY


def _make_icon_image(size: int = 64):
    """Draw a simple shield-style icon so we don't ship a binary asset."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Shield body
    d.polygon(
        [(size * 0.5, size * 0.08), (size * 0.9, size * 0.22),
         (size * 0.9, size * 0.55), (size * 0.5, size * 0.94),
         (size * 0.1, size * 0.55), (size * 0.1, size * 0.22)],
        fill=(33, 150, 243, 255),
    )
    # Check mark
    d.line(
        [(size * 0.32, size * 0.5), (size * 0.46, size * 0.66), (size * 0.72, size * 0.34)],
        fill=(255, 255, 255, 255), width=max(3, size // 14),
    )
    return img


class SystemTray:
    """Wraps a pystray Icon bound to a :class:`Monitor`."""

    def __init__(
        self,
        monitor: Monitor,
        *,
        on_open_dashboard: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
    ) -> None:
        self.monitor = monitor
        self.on_open_dashboard = on_open_dashboard
        self.on_quit = on_quit
        self._icon: Optional["pystray.Icon"] = None
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ #
    def _status_text(self, _item=None) -> str:
        if not self.monitor.running:
            return "Status: stopped"
        if self.monitor.paused:
            return "Status: paused"
        return f"Status: protecting ({self.monitor.stats['tracked_processes']} processes)"

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem("Open ProcAI Dashboard", self._open, default=True),
            pystray.MenuItem(self._status_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Pause monitoring",
                self._toggle_pause,
                checked=lambda item: self.monitor.paused,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit ProcAI", self._quit),
        )

    # ------------------------------------------------------------------ #
    def _open(self, _icon=None, _item=None) -> None:
        if self.on_open_dashboard:
            self.on_open_dashboard()

    def _toggle_pause(self, _icon=None, _item=None) -> None:
        if self.monitor.paused:
            self.monitor.resume()
        else:
            self.monitor.pause()

    def _quit(self, _icon=None, _item=None) -> None:
        try:
            if self.on_quit:
                self.on_quit()
        finally:
            self.stop()

    # ------------------------------------------------------------------ #
    def notify(self, title: str, message: str) -> None:
        if self._icon is not None:
            try:
                self._icon.notify(message, title)
            except Exception as exc:  # pragma: no cover
                log.debug("Tray notify failed: %s", exc)

    # ------------------------------------------------------------------ #
    def run(self) -> None:
        """Run the tray loop (blocking). Use :meth:`run_detached` otherwise."""
        if not _HAVE_TRAY:
            log.warning("pystray/Pillow not installed; tray icon unavailable.")
            return
        self._icon = pystray.Icon(
            "procai", _make_icon_image(), "ProcAI Endpoint Protection", self._build_menu()
        )
        self._icon.run()

    def run_detached(self) -> None:
        if not _HAVE_TRAY:
            log.warning("pystray/Pillow not installed; tray icon unavailable.")
            return
        self._thread = threading.Thread(target=self.run, name="procai-tray", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:  # pragma: no cover
                pass
            self._icon = None
