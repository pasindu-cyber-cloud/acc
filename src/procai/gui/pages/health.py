"""Protection Health page: ProcAI's own status (NOT a Windows Defender spoof).

This page transparently reports ProcAI's protection state: monitoring service,
model status, baseline engine, notifications, tray/background mode, audit-log
integrity and learning progress. It explicitly does not impersonate Microsoft
Defender or claim Windows Security Center provider status.
"""

from __future__ import annotations

import customtkinter as ctk

from .. import theme
from .base import BasePage


class ProtectionHealthPage(BasePage):
    title = "Protection Health"

    def build(self) -> None:
        c = self.content
        c.grid_columnconfigure(0, weight=1)
        c.grid_rowconfigure(1, weight=1)

        self.banner = ctk.CTkFrame(c, fg_color=theme.SURFACE, corner_radius=12)
        self.banner.grid(row=0, column=0, sticky="ew")
        self.banner.grid_columnconfigure(1, weight=1)
        self.banner_icon = ctk.CTkLabel(self.banner, text="\U0001F6E1",
                                        font=(theme.FONT_FAMILY, 40))
        self.banner_icon.grid(row=0, column=0, rowspan=2, padx=18, pady=16)
        self.banner_title = ctk.CTkLabel(self.banner, text="Checking...",
                                         font=theme.FONT_TITLE, anchor="w")
        self.banner_title.grid(row=0, column=1, sticky="w", pady=(16, 0))
        self.banner_sub = ctk.CTkLabel(self.banner, text="", font=theme.FONT_BODY,
                                       text_color=theme.TEXT_MUTED, anchor="w")
        self.banner_sub.grid(row=1, column=1, sticky="w", pady=(0, 16))

        self.grid_area = ctk.CTkScrollableFrame(c, fg_color="transparent")
        self.grid_area.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.grid_area.grid_columnconfigure((0, 1), weight=1, uniform="h")

        ctk.CTkLabel(
            c, text="ProcAI is independent software and does not replace or impersonate "
            "Microsoft Defender. Keep Windows Defender enabled.",
            font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED, wraplength=900,
            justify="left").grid(row=2, column=0, sticky="w", pady=(8, 0))

        self._rows = {}

    # ------------------------------------------------------------------ #
    def _status_card(self, row: int, col: int, title: str):
        card = ctk.CTkFrame(self.grid_area, fg_color=theme.SURFACE, corner_radius=10)
        card.grid(row=row, column=col, sticky="ew", padx=6, pady=6)
        card.grid_columnconfigure(1, weight=1)
        dot = ctk.CTkLabel(card, text="\u25CF", font=(theme.FONT_FAMILY, 16),
                           text_color=theme.TEXT_MUTED, width=24)
        dot.grid(row=0, column=0, padx=(12, 4), pady=10)
        lab = ctk.CTkLabel(card, text=title, font=theme.FONT_SUBHEADING, anchor="w")
        lab.grid(row=0, column=1, sticky="w")
        val = ctk.CTkLabel(card, text="-", font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED,
                           anchor="e")
        val.grid(row=0, column=2, sticky="e", padx=12)
        return dot, val

    def on_show(self) -> None:
        for w in self.grid_area.winfo_children():
            w.destroy()
        self._rows = {
            "monitor": self._status_card(0, 0, "Monitoring service"),
            "psutil": self._status_card(0, 1, "Telemetry (psutil)"),
            "model": self._status_card(1, 0, "ML model"),
            "baseline": self._status_card(1, 1, "Baseline engine"),
            "notify": self._status_card(2, 0, "Desktop notifications"),
            "tray": self._status_card(2, 1, "Tray / background mode"),
            "learning": self._status_card(3, 0, "Learning mode"),
            "audit": self._status_card(3, 1, "Audit-log integrity"),
        }

        h = self.app.engine.health()
        mon = self.app.monitor

        def set_row(key, ok, text, warn=False):
            dot, val = self._rows[key]
            color = theme.SUCCESS if ok else (theme.WARNING if warn else theme.TEXT_MUTED)
            dot.configure(text_color=color)
            val.configure(text=text, text_color=color)

        running = mon.running and not mon.paused
        set_row("monitor", running,
                "Protecting" if running else ("Paused" if mon.paused else "Stopped"),
                warn=not running)
        set_row("psutil", h["psutil_available"],
                "Available" if h["psutil_available"] else "Not installed", warn=not h["psutil_available"])
        set_row("model", h["model_loaded"],
                f"Loaded ({h['model_name']})" if h["model_loaded"]
                else ("Available, not trained" if h["ml_available"] else "ML not installed"),
                warn=not h["model_loaded"])
        set_row("baseline", h["baseline_identities"] > 0,
                f"{h['baseline_identities']} programs learned")
        set_row("notify", self.app.settings.desktop_notifications,
                "On" if self.app.settings.desktop_notifications else "Off")
        from ...service.tray import tray_available
        set_row("tray", tray_available(),
                "Available" if tray_available() else "Install procai[gui]")
        set_row("learning", True,
                f"{h['learning_remaining_min']} min left" if h["learning_active"] else "Complete")
        set_row("audit", h["audit_ok"], "Verified" if h["audit_ok"] else "TAMPER DETECTED",
                warn=not h["audit_ok"])

        # Banner summary
        if running and h["audit_ok"]:
            self.banner_title.configure(text="You're protected", text_color=theme.SUCCESS)
            self.banner_sub.configure(text="ProcAI is actively monitoring process behaviour.")
        elif not running:
            self.banner_title.configure(text="Protection is off", text_color=theme.WARNING)
            self.banner_sub.configure(text="Start protection from the sidebar to begin monitoring.")
        else:
            self.banner_title.configure(text="Attention needed", text_color=theme.WARNING)
            self.banner_sub.configure(text="Review the items below.")
