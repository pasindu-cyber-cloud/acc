"""Deep Scan: a focused local review surfacing the riskiest findings.

This runs a full scan and then groups noteworthy findings: unsigned binaries in
unusual locations, suspicious parent-child chains, high-resource processes, and
processes with heavy network activity. It is read-only analysis.
"""

from __future__ import annotations

import threading

import customtkinter as ctk

from .. import theme
from ..widgets import SeverityBadge
from ...core.models import Severity
from .base import BasePage


class DeepScanPage(BasePage):
    title = "Deep Scan"

    def build(self) -> None:
        c = self.content
        c.grid_rowconfigure(2, weight=1)

        bar = ctk.CTkFrame(c, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.scan_btn = ctk.CTkButton(bar, text="Run Deep Scan", width=160,
                                      command=self._run)
        self.scan_btn.pack(side="left")
        ctk.CTkButton(bar, text="Run on simulation data", fg_color=theme.SURFACE_2,
                      hover_color="#2E3B49", command=lambda: self._run(simulate=True)).pack(
            side="left", padx=8)
        self.status = ctk.CTkLabel(bar, text="", text_color=theme.TEXT_MUTED,
                                   font=theme.FONT_SMALL)
        self.status.pack(side="left", padx=8)

        self.summary = ctk.CTkLabel(c, text="", font=theme.FONT_BODY, anchor="w",
                                    justify="left")
        self.summary.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        self.findings = ctk.CTkScrollableFrame(c, fg_color=theme.SURFACE, corner_radius=12)
        self.findings.grid(row=2, column=0, sticky="nsew")
        self.findings.grid_columnconfigure(0, weight=1)

    # ------------------------------------------------------------------ #
    def on_show(self) -> None:
        pass

    def _run(self, simulate: bool = False) -> None:
        self.scan_btn.configure(state="disabled")
        self.status.configure(text="Scanning...")

        def work():
            if simulate:
                import procai.core.simulation as simulation
                results = self.app.engine.scan_once(simulation.generate(),
                                                    enrich_reputation=False)
            else:
                results = self.app.engine.scan_once()
            self.after(0, lambda: self._render(results))

        threading.Thread(target=work, daemon=True).start()

    def _render(self, results) -> None:
        self.scan_btn.configure(state="normal")
        self.status.configure(text=f"Scanned {len(results)} processes.")
        for w in self.findings.winfo_children():
            w.destroy()

        groups = {
            "Unsigned / suspicious-location executables": [
                r for r in results
                if r.snapshot.is_signed is False or r.snapshot.in_suspicious_dir],
            "Unusual parent-child chains": [
                r for r in results
                if any(h.rule_id.startswith("lineage") for h in r.rule_hits)],
            "High resource usage": [
                r for r in results
                if r.snapshot.cpu_percent >= 60 or r.snapshot.memory_mb >= 1024
                or r.snapshot.num_threads >= 200],
            "Heavy network activity": [
                r for r in results if r.snapshot.num_connections >= 20],
            "Startup-persistent items": [
                r for r in results if r.snapshot.is_startup_persistent],
        }

        flagged = sum(1 for r in results if r.severity >= Severity.MEDIUM)
        self.summary.configure(
            text=f"Findings: {flagged} process(es) at MEDIUM+ risk. "
                 "Review the grouped findings below.")

        row = 0
        any_finding = False
        for title, items in groups.items():
            if not items:
                continue
            any_finding = True
            header = ctk.CTkLabel(self.findings, text=f"{title}  ({len(items)})",
                                  font=theme.FONT_SUBHEADING, anchor="w")
            header.grid(row=row, column=0, sticky="w", padx=12, pady=(12, 2))
            row += 1
            for r in sorted(items, key=lambda x: x.risk_score, reverse=True)[:25]:
                s = r.snapshot
                card = ctk.CTkFrame(self.findings, fg_color=theme.SURFACE_2, corner_radius=8)
                card.grid(row=row, column=0, sticky="ew", padx=10, pady=2)
                card.grid_columnconfigure(1, weight=1)
                SeverityBadge(card, r.severity).grid(row=0, column=0, padx=8, pady=6)
                detail = f"{s.name} (PID {s.pid})  -  risk {r.risk_score:.0f}  -  {s.exe_path}"
                ctk.CTkLabel(card, text=detail, font=theme.FONT_SMALL, anchor="w").grid(
                    row=0, column=1, sticky="w")
                ctk.CTkButton(card, text="Inspect", width=80,
                              command=lambda pid=s.pid: self._inspect(pid)).grid(
                    row=0, column=2, padx=8)
                row += 1

        if not any_finding:
            ctk.CTkLabel(self.findings, text="No noteworthy findings. System looks clean.",
                         text_color=theme.SUCCESS, font=theme.FONT_BODY).grid(
                row=0, column=0, padx=12, pady=12, sticky="w")

    def _inspect(self, pid: int) -> None:
        self.app.show_page("intelligence")
        page = self.app._pages.get("intelligence")
        if page:
            page.inspect_pid(pid)
