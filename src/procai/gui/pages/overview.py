"""Overview dashboard: protection status, key metrics, recent alerts, resources."""

from __future__ import annotations

import time

import customtkinter as ctk

from .. import theme
from ..widgets import StatCard, SeverityBadge
from ...core.models import Severity
from .base import BasePage


class OverviewPage(BasePage):
    title = "Overview"

    def build(self) -> None:
        c = self.content
        c.grid_rowconfigure(2, weight=1)

        # --- Stat cards row ---
        cards = ctk.CTkFrame(c, fg_color="transparent")
        cards.grid(row=0, column=0, sticky="ew")
        for i in range(4):
            cards.grid_columnconfigure(i, weight=1, uniform="cards")
        self.card_status = StatCard(cards, "Protection", "Stopped", accent=theme.TEXT_MUTED)
        self.card_scanned = StatCard(cards, "Processes Scanned", "0", accent=theme.PRIMARY)
        self.card_alerts = StatCard(cards, "Suspicious (24h)", "0", accent=theme.WARNING)
        self.card_conf = StatCard(cards, "Model Confidence", "-", accent=theme.SUCCESS)
        for i, card in enumerate(
            (self.card_status, self.card_scanned, self.card_alerts, self.card_conf)
        ):
            card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))

        # --- Resource row ---
        res = ctk.CTkFrame(c, fg_color="transparent")
        res.grid(row=1, column=0, sticky="ew", pady=(10, 10))
        for i in range(3):
            res.grid_columnconfigure(i, weight=1, uniform="res")
        self.card_cpu = StatCard(res, "System CPU", "-", accent=theme.PRIMARY)
        self.card_mem = StatCard(res, "System Memory", "-", accent=theme.PRIMARY)
        self.card_learn = StatCard(res, "Learning Mode", "-", accent=theme.SUCCESS)
        for i, card in enumerate((self.card_cpu, self.card_mem, self.card_learn)):
            card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))

        # --- Recent alerts panel ---
        panel = ctk.CTkFrame(c, fg_color=theme.SURFACE, corner_radius=12)
        panel.grid(row=2, column=0, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(panel, text="Recent Alerts", font=theme.FONT_HEADING).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 6))
        self.alerts_list = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        self.alerts_list.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 12))
        self.alerts_list.grid_columnconfigure(0, weight=1)

    # ------------------------------------------------------------------ #
    def on_show(self) -> None:
        mon = self.app.monitor
        stats = mon.stats
        running = stats["running"] and not stats["paused"]
        self.card_status.set(
            "Protected" if running else ("Paused" if stats["paused"] else "Stopped"),
            subtitle=f"{stats['scan_count']} scans",
            accent=theme.SUCCESS if running else theme.TEXT_MUTED,
        )
        self.card_scanned.set(str(int(stats["tracked_processes"])), subtitle="this scan")

        since = time.time() - 86400
        counts = self.app.engine.db.alert_counts_by_severity(since=since)
        total = sum(counts.values())
        high = counts.get(int(Severity.HIGH), 0) + counts.get(int(Severity.CRITICAL), 0)
        self.card_alerts.set(str(total), subtitle=f"{high} high/critical",
                             accent=theme.SEVERITY_COLORS[Severity.HIGH] if high else theme.WARNING)

        health = self.app.engine.health()
        if health["model_loaded"]:
            self.card_conf.set("Active", subtitle=str(health["model_name"]))
        else:
            self.card_conf.set("Rules+Stats", subtitle="ML model not trained")

        ov = self.app.engine.system_overview()
        if ov:
            self.card_cpu.set(f"{ov.get('cpu_percent', 0):.0f}%")
            self.card_mem.set(f"{ov.get('memory_percent', 0):.0f}%",
                              subtitle=f"{ov.get('memory_used_gb', 0):.1f} / "
                                       f"{ov.get('memory_total_gb', 0):.1f} GB")
        else:
            self.card_cpu.set("n/a", subtitle="psutil not installed")
            self.card_mem.set("n/a")

        if health["learning_active"]:
            self.card_learn.set("Learning", subtitle=f"{health['learning_remaining_min']} min left",
                                accent=theme.WARNING)
        else:
            self.card_learn.set("Active", subtitle=f"{health['baseline_identities']} baselines")

        self._render_recent_alerts()

    def _render_recent_alerts(self) -> None:
        for w in self.alerts_list.winfo_children():
            w.destroy()
        alerts = self.app.engine.db.get_alerts(limit=12)
        if not alerts:
            ctk.CTkLabel(self.alerts_list, text="No alerts yet. You're all clear.",
                         text_color=theme.TEXT_MUTED, font=theme.FONT_BODY).grid(
                row=0, column=0, sticky="w", padx=12, pady=12)
            return
        for i, a in enumerate(alerts):
            row = ctk.CTkFrame(self.alerts_list, fg_color=theme.SURFACE_2, corner_radius=8)
            row.grid(row=i, column=0, sticky="ew", padx=6, pady=3)
            row.grid_columnconfigure(1, weight=1)
            SeverityBadge(row, a.severity).grid(row=0, column=0, padx=10, pady=8)
            txt = f"{a.process_name} (PID {a.pid})  -  risk {a.risk_score:.0f}"
            ctk.CTkLabel(row, text=txt, font=theme.FONT_BODY, anchor="w").grid(
                row=0, column=1, sticky="w")
            when = time.strftime("%H:%M:%S", time.localtime(a.timestamp))
            ctk.CTkLabel(row, text=when, font=theme.FONT_SMALL,
                         text_color=theme.TEXT_MUTED).grid(row=0, column=2, padx=12)
