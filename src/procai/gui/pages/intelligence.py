"""Process Intelligence: full explainable breakdown of one process."""

from __future__ import annotations

import customtkinter as ctk

from .. import theme
from ..widgets import RiskBar, SeverityBadge
from ...assistant.explain import explain_detection, investigation_guide
from ...core.models import DetectionResult
from .base import BasePage


class IntelligencePage(BasePage):
    title = "Process Intelligence"

    def build(self) -> None:
        c = self.content
        c.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(c, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ctk.CTkLabel(bar, text="PID:", text_color=theme.TEXT_MUTED).pack(side="left")
        self.pid_entry = ctk.CTkEntry(bar, width=120, placeholder_text="e.g. 1234")
        self.pid_entry.pack(side="left", padx=8)
        ctk.CTkButton(bar, text="Inspect", width=100,
                      command=self._inspect_from_entry).pack(side="left")
        self.badge = SeverityBadge(bar)
        self.badge.pack(side="right", padx=6)
        self.risk = RiskBar(bar, width=180)
        self.risk.pack(side="right", padx=6)

        body = ctk.CTkFrame(c, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(body, fg_color=theme.SURFACE, corner_radius=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(left, text="Explanation", font=theme.FONT_HEADING).grid(
            row=0, column=0, sticky="w", padx=14, pady=(12, 4))
        self.explain_box = ctk.CTkTextbox(left, font=theme.FONT_BODY, wrap="word",
                                          fg_color=theme.SURFACE_2)
        self.explain_box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        right = ctk.CTkFrame(body, fg_color=theme.SURFACE, corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(right, text="Investigation Guide", font=theme.FONT_HEADING).grid(
            row=0, column=0, sticky="w", padx=14, pady=(12, 4))
        self.guide_box = ctk.CTkScrollableFrame(right, fg_color="transparent")
        self.guide_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 12))
        self.guide_box.grid_columnconfigure(0, weight=1)

        self._set_placeholder()

    # ------------------------------------------------------------------ #
    def _set_placeholder(self) -> None:
        self.explain_box.delete("1.0", "end")
        self.explain_box.insert(
            "1.0", "Enter a PID and click Inspect, or double-click a process on the "
            "Live Processes page.")

    def _inspect_from_entry(self) -> None:
        try:
            pid = int(self.pid_entry.get().strip())
        except ValueError:
            return
        self.inspect_pid(pid)

    def inspect_pid(self, pid: int) -> None:
        self.pid_entry.delete(0, "end")
        self.pid_entry.insert(0, str(pid))
        result = self.app.engine.inspect(pid)
        if result is None:
            # Fall back to the most recent monitored result for that PID.
            result = next((r for r in self.app.monitor.last_results
                           if r.snapshot.pid == pid), None)
        if result is None:
            self.explain_box.delete("1.0", "end")
            self.explain_box.insert("1.0", f"Could not inspect PID {pid} (it may have exited "
                                    "or require elevation).")
            return
        self._render(result)

    def _render(self, result: DetectionResult) -> None:
        self.badge.set_severity(result.severity)
        self.risk.set_score(result.risk_score)
        self.explain_box.delete("1.0", "end")
        self.explain_box.insert("1.0", explain_detection(result))

        for w in self.guide_box.winfo_children():
            w.destroy()
        for i, step in enumerate(investigation_guide(result), start=1):
            row = ctk.CTkFrame(self.guide_box, fg_color=theme.SURFACE_2, corner_radius=8)
            row.grid(row=i, column=0, sticky="ew", padx=4, pady=3)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text=str(i), width=24, font=theme.FONT_SUBHEADING,
                         text_color=theme.PRIMARY).grid(row=0, column=0, padx=(8, 4), pady=6)
            ctk.CTkLabel(row, text=step, font=theme.FONT_SMALL, wraplength=320,
                         justify="left", anchor="w").grid(row=0, column=1, sticky="w", pady=6,
                                                          padx=(0, 8))
