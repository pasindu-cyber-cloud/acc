"""Reports page: export alerts/history to CSV or PDF and open the reports folder."""

from __future__ import annotations

import os
import subprocess
import sys
import time

import customtkinter as ctk

from .. import theme
from ... import reports
from ...config import PATHS
from .base import BasePage


class ReportsPage(BasePage):
    title = "Reports"

    def build(self) -> None:
        c = self.content
        c.grid_columnconfigure(0, weight=1)

        panel = ctk.CTkFrame(c, fg_color=theme.SURFACE, corner_radius=12)
        panel.grid(row=0, column=0, sticky="ew")
        panel.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(panel, text="Export data", font=theme.FONT_HEADING).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 4))
        ctk.CTkLabel(panel, text="Reports are generated locally and saved to your reports "
                     "folder. No data leaves this machine.", font=theme.FONT_SMALL,
                     text_color=theme.TEXT_MUTED).grid(row=1, column=0, sticky="w", padx=16)

        btns = ctk.CTkFrame(panel, fg_color="transparent")
        btns.grid(row=2, column=0, sticky="w", padx=12, pady=12)
        ctk.CTkButton(btns, text="Export alerts (CSV)", width=180,
                      command=self._alerts_csv).grid(row=0, column=0, padx=6, pady=6)
        self.pdf_btn = ctk.CTkButton(btns, text="Export alerts (PDF)", width=180,
                                     command=self._alerts_pdf)
        self.pdf_btn.grid(row=0, column=1, padx=6, pady=6)
        ctk.CTkButton(btns, text="Export process history (CSV)", width=220,
                      command=self._history_csv).grid(row=0, column=2, padx=6, pady=6)
        ctk.CTkButton(btns, text="Open reports folder", width=180, fg_color=theme.SURFACE_2,
                      hover_color="#2E3B49", command=self._open_folder).grid(
            row=1, column=0, padx=6, pady=6)

        self.status = ctk.CTkLabel(c, text="", font=theme.FONT_BODY, anchor="w",
                                   justify="left", text_color=theme.SUCCESS)
        self.status.grid(row=1, column=0, sticky="ew", pady=(12, 0))

        self.recent = ctk.CTkScrollableFrame(c, fg_color=theme.SURFACE, corner_radius=12,
                                             height=300)
        self.recent.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        self.recent.grid_columnconfigure(0, weight=1)
        c.grid_rowconfigure(2, weight=1)

    # ------------------------------------------------------------------ #
    def on_show(self) -> None:
        self.pdf_btn.configure(state="normal" if reports.pdf_available() else "disabled")
        if not reports.pdf_available():
            self.pdf_btn.configure(text="PDF (install procai[reports])")
        self._list_recent()

    def _alerts_csv(self) -> None:
        alerts = self.app.engine.db.get_alerts(limit=10000)
        path = reports.export_alerts_csv(alerts)
        self._done(path)

    def _alerts_pdf(self) -> None:
        alerts = self.app.engine.db.get_alerts(limit=5000)
        summary = {
            "Total alerts": len(alerts),
            "Generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "Sensitivity": self.app.settings.sensitivity.value,
        }
        try:
            path = reports.export_alerts_pdf(alerts, summary=summary)
            self._done(path)
        except RuntimeError as exc:
            self.status.configure(text=str(exc), text_color=theme.WARNING)

    def _history_csv(self) -> None:
        rows = self.app.engine.db.recent_process_history(limit=20000)
        path = reports.export_process_history_csv(rows)
        self._done(path)

    def _done(self, path) -> None:
        self.status.configure(text=f"Saved: {path}", text_color=theme.SUCCESS)
        self._list_recent()

    def _open_folder(self) -> None:
        path = str(PATHS.reports_dir)
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            self.status.configure(text=f"Reports folder: {path}", text_color=theme.TEXT_MUTED)

    def _list_recent(self) -> None:
        for w in self.recent.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.recent, text="Generated reports", font=theme.FONT_SUBHEADING).grid(
            row=0, column=0, sticky="w", padx=10, pady=(8, 4))
        try:
            files = sorted(PATHS.reports_dir.glob("*"), key=lambda p: p.stat().st_mtime,
                           reverse=True)
        except OSError:
            files = []
        if not files:
            ctk.CTkLabel(self.recent, text="No reports generated yet.",
                         text_color=theme.TEXT_MUTED).grid(row=1, column=0, sticky="w",
                                                          padx=10, pady=6)
            return
        for i, f in enumerate(files[:50], start=1):
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(f.stat().st_mtime))
            ctk.CTkLabel(self.recent, text=f"{f.name}    ({when})", font=theme.FONT_SMALL,
                         anchor="w").grid(row=i, column=0, sticky="w", padx=12, pady=2)
