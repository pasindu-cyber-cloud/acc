"""ProcAIApp: the main GUI controller (CustomTkinter).

Owns the shared engine, monitor and notifier, builds the sidebar + page area,
and coordinates navigation, the first-run consent flow, live refresh, alert
toasts and (optional) tray minimisation.

Run with ``python -m procai`` or the ``procai`` console script.
"""

from __future__ import annotations

import logging
import queue
from typing import Optional

from ..config import CONSENT_VERSION, Settings
from ..core.engine import ProcAIEngine
from ..core.models import Alert, DetectionResult, Severity
from ..core.monitor import Monitor
from ..service.notifications import Notifier
from ..utils import audit
from ..utils.logging_setup import configure, get_logger

log = get_logger("gui.app")


def run() -> int:
    """Import the GUI toolkit and launch the app. Returns a process exit code."""
    configure(level=logging.INFO)
    try:
        import customtkinter as ctk  # noqa: F401
    except Exception as exc:  # pragma: no cover
        print(
            "ProcAI GUI requires customtkinter. Install GUI extras:\n"
            "    pip install procai[gui]\n"
            f"(import error: {exc})"
        )
        return 1
    app = ProcAIApp()
    app.mainloop()
    return 0


def _build_app_class():
    """Define ProcAIApp lazily so importing this module never needs customtkinter."""
    import customtkinter as ctk

    from . import theme
    from .pages.alerts import AlertsPage
    from .pages.assistant import AssistantPage
    from .pages.deep_scan import DeepScanPage
    from .pages.health import ProtectionHealthPage
    from .pages.intelligence import IntelligencePage
    from .pages.live_processes import LiveProcessesPage
    from .pages.overview import OverviewPage
    from .pages.reports import ReportsPage
    from .pages.settings import SettingsPage
    from .pages.timeline import TimelinePage
    from .widgets import Toast

    _PAGE_CLASSES = {
        "overview": OverviewPage,
        "live": LiveProcessesPage,
        "alerts": AlertsPage,
        "intelligence": IntelligencePage,
        "deep_scan": DeepScanPage,
        "timeline": TimelinePage,
        "assistant": AssistantPage,
        "reports": ReportsPage,
        "settings": SettingsPage,
        "health": ProtectionHealthPage,
    }

    class ProcAIApp(ctk.CTk):
        def __init__(self) -> None:
            super().__init__()
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("blue")

            self.title("ProcAI - Endpoint Protection")
            self.geometry("1280x820")
            self.minsize(1040, 680)
            self.configure(fg_color=theme.BG)

            # Shared backend
            self.settings: Settings = Settings.load()
            self.engine = ProcAIEngine(settings=self.settings)
            self.monitor = Monitor(self.engine)
            self.notifier = Notifier(self.settings)

            # Thread-safe queue for alerts raised on the monitor thread.
            self._alert_queue: "queue.Queue[tuple[Alert, DetectionResult]]" = queue.Queue()
            self.engine.add_alert_callback(self._enqueue_alert)

            self._pages: dict[str, object] = {}
            self._current_key: Optional[str] = None
            self._nav_buttons: dict[str, ctk.CTkButton] = {}
            self._tray = None

            self._build_layout()

            # First-run consent gate.
            if not self.settings.consent_accepted:
                self.after(200, self._show_consent)
            else:
                self._post_consent_start()

            self.protocol("WM_DELETE_WINDOW", self._on_close)
            self._poll_alerts()
            self._tick()

        # -------------------------------------------------------------- #
        # Layout
        # -------------------------------------------------------------- #
        def _build_layout(self) -> None:
            self.grid_columnconfigure(1, weight=1)
            self.grid_rowconfigure(0, weight=1)
            self._build_sidebar()

            self.page_container = ctk.CTkFrame(self, fg_color=theme.BG)
            self.page_container.grid(row=0, column=1, sticky="nsew")
            self.page_container.grid_columnconfigure(0, weight=1)
            self.page_container.grid_rowconfigure(0, weight=1)

        def _build_sidebar(self) -> None:
            bar = ctk.CTkFrame(self, width=240, corner_radius=0, fg_color=theme.SIDEBAR)
            bar.grid(row=0, column=0, sticky="nsw")
            bar.grid_propagate(False)
            bar.grid_rowconfigure(99, weight=1)

            # Brand
            brand = ctk.CTkFrame(bar, fg_color="transparent")
            brand.grid(row=0, column=0, sticky="ew", padx=18, pady=(20, 6))
            ctk.CTkLabel(brand, text="\U0001F6E1  ProcAI",
                         font=(theme.FONT_FAMILY, 20, "bold")).pack(anchor="w")
            ctk.CTkLabel(brand, text="Endpoint Protection", font=theme.FONT_SMALL,
                         text_color=theme.TEXT_MUTED).pack(anchor="w")

            # Protection status chip
            self._status_chip = ctk.CTkLabel(
                bar, text="\u25CF  Stopped", font=theme.FONT_SMALL,
                fg_color=theme.SURFACE_2, corner_radius=8, text_color=theme.TEXT_MUTED,
                height=30)
            self._status_chip.grid(row=1, column=0, sticky="ew", padx=18, pady=(8, 14))

            for i, (key, label, glyph) in enumerate(theme.NAV_ITEMS, start=2):
                btn = ctk.CTkButton(
                    bar, text=f"  {glyph}   {label}", anchor="w", height=40,
                    corner_radius=8, fg_color="transparent", text_color=theme.TEXT,
                    hover_color=theme.SURFACE_2, font=theme.FONT_BODY,
                    command=lambda k=key: self.show_page(k))
                btn.grid(row=i, column=0, sticky="ew", padx=12, pady=2)
                self._nav_buttons[key] = btn

            # Monitoring toggle at the bottom
            self._toggle_btn = ctk.CTkButton(
                bar, text="Start Protection", height=42, corner_radius=10,
                fg_color=theme.SUCCESS, hover_color="#27AE60",
                font=theme.FONT_SUBHEADING, command=self.toggle_monitoring)
            self._toggle_btn.grid(row=100, column=0, sticky="ew", padx=14, pady=(8, 8))
            ctk.CTkLabel(bar, text=f"v2.0.0  -  privacy-first", font=theme.FONT_SMALL,
                         text_color=theme.TEXT_MUTED).grid(row=101, column=0, pady=(0, 12))

        # -------------------------------------------------------------- #
        # Navigation
        # -------------------------------------------------------------- #
        def show_page(self, key: str) -> None:
            if key not in _PAGE_CLASSES:
                return
            if key not in self._pages:
                page = _PAGE_CLASSES[key](self.page_container, self)
                page.grid(row=0, column=0, sticky="nsew")
                self._pages[key] = page
            page = self._pages[key]
            page.tkraise()
            self._current_key = key
            for k, btn in self._nav_buttons.items():
                btn.configure(fg_color=theme.PRIMARY if k == key else "transparent")
            try:
                page.on_show()
            except Exception as exc:  # a page refresh error must not break navigation
                log.exception("Page %s on_show failed: %s", key, exc)

        # -------------------------------------------------------------- #
        # Consent flow
        # -------------------------------------------------------------- #
        def _show_consent(self) -> None:
            from .consent import ConsentDialog

            ConsentDialog(self, on_accept=self._accept_consent, on_decline=self.destroy)

        def _accept_consent(self) -> None:
            self.settings.consent_accepted = True
            self.settings.consent_version = CONSENT_VERSION
            self.settings.save()
            self.engine.update_settings(self.settings)
            audit.record("consent.accept", {"version": CONSENT_VERSION})
            self._post_consent_start()

        def _post_consent_start(self) -> None:
            self.show_page("overview")
            # Auto-start protection unless the user prefers otherwise.
            self.toggle_monitoring(force_start=True)

        # -------------------------------------------------------------- #
        # Monitoring control
        # -------------------------------------------------------------- #
        def toggle_monitoring(self, force_start: bool = False) -> None:
            if self.monitor.running and not force_start:
                self.monitor.stop()
            elif not self.monitor.running:
                self.monitor.start()
            self._refresh_status_chip()

        def _refresh_status_chip(self) -> None:
            if self.monitor.running and not self.monitor.paused:
                self._status_chip.configure(text="\u25CF  Protected", text_color=theme.SUCCESS)
                self._toggle_btn.configure(text="Stop Protection", fg_color="#C0392B",
                                           hover_color="#A93226")
            elif self.monitor.running and self.monitor.paused:
                self._status_chip.configure(text="\u25CF  Paused", text_color=theme.WARNING)
                self._toggle_btn.configure(text="Stop Protection", fg_color="#C0392B",
                                           hover_color="#A93226")
            else:
                self._status_chip.configure(text="\u25CF  Stopped", text_color=theme.TEXT_MUTED)
                self._toggle_btn.configure(text="Start Protection", fg_color=theme.SUCCESS,
                                           hover_color="#27AE60")

        # -------------------------------------------------------------- #
        # Settings propagation
        # -------------------------------------------------------------- #
        def apply_settings(self, new_settings: Settings) -> None:
            self.settings = new_settings
            self.engine.update_settings(new_settings)
            self.notifier.settings = new_settings

        # -------------------------------------------------------------- #
        # Alert plumbing (thread-safe)
        # -------------------------------------------------------------- #
        def _enqueue_alert(self, alert: Alert, result: DetectionResult) -> None:
            self._alert_queue.put((alert, result))

        def _poll_alerts(self) -> None:
            try:
                while True:
                    alert, _result = self._alert_queue.get_nowait()
                    self._handle_alert_ui(alert)
            except queue.Empty:
                pass
            self.after(700, self._poll_alerts)

        def _handle_alert_ui(self, alert: Alert) -> None:
            self.notifier.notify_alert(alert)
            if alert.severity >= Severity.HIGH:
                try:
                    Toast(self, f"{alert.severity.label}: {alert.process_name}",
                          alert.recommended_action, alert.severity)
                except Exception:
                    pass
            # Refresh alerts/overview if visible.
            if self._current_key in ("alerts", "overview"):
                page = self._pages.get(self._current_key)
                if page:
                    page.on_show()

        # -------------------------------------------------------------- #
        # Periodic tick
        # -------------------------------------------------------------- #
        def _tick(self) -> None:
            self._refresh_status_chip()
            if self._current_key in ("overview", "live", "health"):
                page = self._pages.get(self._current_key)
                if page:
                    try:
                        page.on_show()
                    except Exception:
                        pass
            self.after(3000, self._tick)

        # -------------------------------------------------------------- #
        def _ensure_tray(self) -> bool:
            """Create the tray icon on demand. Returns True if a tray is active."""
            from ..service.tray import SystemTray, tray_available

            if self._tray is not None:
                return True
            if not tray_available():
                return False
            self._tray = SystemTray(
                self.monitor,
                on_open_dashboard=lambda: self.after(0, self._restore_from_tray),
                on_quit=lambda: self.after(0, self._quit_app),
            )
            self.notifier.set_backend(self._tray.notify)
            self._tray.run_detached()
            return True

        def _restore_from_tray(self) -> None:
            try:
                self.deiconify()
                self.lift()
                self.focus_force()
            except Exception:
                pass

        def _quit_app(self) -> None:
            try:
                self.monitor.stop()
                if self._tray is not None:
                    self._tray.stop()
                self.engine.close()
            finally:
                self.destroy()

        def _on_close(self) -> None:
            # Minimise to tray (keep protecting) only if a tray icon is available.
            if self.settings.start_minimized_to_tray and self._ensure_tray():
                self.notifier.notify(
                    "ProcAI is still protecting",
                    "ProcAI minimised to the system tray. Right-click the tray icon to "
                    "open the dashboard or quit.",
                )
                self.withdraw()
                return
            self._quit_app()

    return ProcAIApp


# Lazily-built class proxy so `ProcAIApp()` works after customtkinter import.
def ProcAIApp(*args, **kwargs):  # noqa: N802 - factory mimicking a class
    cls = _build_app_class()
    return cls(*args, **kwargs)
