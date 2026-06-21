"""Forensic Timeline: chronological view of alerts and process-history events."""

from __future__ import annotations

import time
from tkinter import ttk

import customtkinter as ctk

from .. import theme
from ...core.models import Severity
from .base import BasePage
from .live_processes import style_treeview

_COLS = [
    ("time", "Time", 160),
    ("type", "Event", 110),
    ("severity", "Severity", 90),
    ("process", "Process", 200),
    ("detail", "Detail", 460),
]


class TimelinePage(BasePage):
    title = "Forensic Timeline"

    def build(self) -> None:
        style_treeview()
        c = self.content
        c.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(c, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ctk.CTkLabel(bar, text="Window:", text_color=theme.TEXT_MUTED).pack(side="left")
        self.window = ctk.CTkOptionMenu(bar, values=["Last hour", "Last 24h", "Last 7 days"],
                                        width=140, command=lambda _v: self._refresh())
        self.window.set("Last 24h")
        self.window.pack(side="left", padx=8)
        ctk.CTkButton(bar, text="Refresh", width=90, command=self._refresh).pack(side="left")

        wrap = ctk.CTkFrame(c, fg_color=theme.SURFACE, corner_radius=12)
        wrap.grid(row=1, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(0, weight=1)
        cols = [x[0] for x in _COLS]
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", style="ProcAI.Treeview")
        for key, label, width in _COLS:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w")
        for sev in Severity:
            self.tree.tag_configure(sev.name, foreground=theme.severity_color(sev))
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        vsb.grid(row=0, column=1, sticky="ns", pady=8, padx=(0, 8))

    # ------------------------------------------------------------------ #
    def on_show(self) -> None:
        self._refresh()

    def _since(self) -> float:
        return {
            "Last hour": time.time() - 3600,
            "Last 24h": time.time() - 86400,
            "Last 7 days": time.time() - 7 * 86400,
        }[self.window.get()]

    def _refresh(self) -> None:
        since = self._since()
        db = self.app.engine.db
        events = []
        for a in db.get_alerts(limit=500, since=since):
            events.append((a.timestamp, "Alert", a.severity, a.process_name,
                           (a.reasons[0] if a.reasons else a.recommended_action)[:90]))
        # Notable process-history rows (flagged ones only, to keep it readable).
        for row in db.recent_process_history(limit=400):
            if row.get("ts", 0) < since:
                continue
            if (row.get("severity") or 0) >= int(Severity.MEDIUM):
                events.append((row["ts"], "Process", Severity(int(row["severity"])),
                               row["name"],
                               f"risk {row.get('risk_score', 0):.0f}, "
                               f"cpu {row.get('cpu_percent', 0):.0f}%, "
                               f"{row.get('exe_path') or ''}"[:90]))

        events.sort(key=lambda e: e[0], reverse=True)
        self.tree.delete(*self.tree.get_children())
        for ts, etype, sev, proc, detail in events[:600]:
            when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
            self.tree.insert("", "end",
                             values=(when, etype, sev.label, proc, detail),
                             tags=(sev.name,))
