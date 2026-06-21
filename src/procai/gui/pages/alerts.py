"""Alerts page: severity-coloured alert table with detail and acknowledge."""

from __future__ import annotations

import time
from tkinter import ttk

import customtkinter as ctk

from .. import theme
from ...core.models import Severity
from .base import BasePage
from .live_processes import style_treeview

_COLS = [
    ("time", "Time", 140),
    ("severity", "Severity", 90),
    ("name", "Process", 180),
    ("pid", "PID", 70),
    ("risk", "Risk", 60),
    ("reason", "Top reason", 380),
    ("status", "Status", 90),
]


class AlertsPage(BasePage):
    title = "Alerts"

    def build(self) -> None:
        style_treeview()
        c = self.content
        c.grid_rowconfigure(1, weight=1)
        c.grid_columnconfigure(0, weight=3)
        c.grid_columnconfigure(1, weight=2)

        # Toolbar
        bar = ctk.CTkFrame(c, fg_color="transparent")
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ctk.CTkLabel(bar, text="Filter:", text_color=theme.TEXT_MUTED).pack(side="left")
        self.filter = ctk.CTkOptionMenu(
            bar, values=["All", "Critical", "High", "Medium", "Low", "Unacknowledged"],
            width=160, command=lambda _v: self._refresh())
        self.filter.pack(side="left", padx=8)
        ctk.CTkButton(bar, text="Acknowledge", width=120,
                      command=self._acknowledge).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="Add to allowlist", width=130, fg_color=theme.SURFACE_2,
                      hover_color="#2E3B49", command=self._allowlist).pack(side="left", padx=4)

        # Table
        wrap = ctk.CTkFrame(c, fg_color=theme.SURFACE, corner_radius=12)
        wrap.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
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
        self.tree.bind("<<TreeviewSelect>>", self._show_detail)

        # Detail panel
        detail = ctk.CTkFrame(c, fg_color=theme.SURFACE, corner_radius=12)
        detail.grid(row=1, column=1, sticky="nsew")
        detail.grid_columnconfigure(0, weight=1)
        detail.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(detail, text="Alert Detail", font=theme.FONT_HEADING).grid(
            row=0, column=0, sticky="w", padx=14, pady=(12, 4))
        self.detail = ctk.CTkTextbox(detail, font=theme.FONT_BODY, wrap="word",
                                     fg_color=theme.SURFACE_2)
        self.detail.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.detail.insert("1.0", "Select an alert to see details.")
        self.detail.configure(state="disabled")

        self._alerts = []
        self._by_iid = {}

    # ------------------------------------------------------------------ #
    def on_show(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        f = self.filter.get()
        kwargs = {"limit": 500}
        if f == "Unacknowledged":
            kwargs["unacknowledged_only"] = True
        elif f in ("Critical", "High", "Medium", "Low"):
            kwargs["min_severity"] = Severity.from_name(f)
        self._alerts = self.app.engine.db.get_alerts(**kwargs)
        if f in ("Critical", "High", "Medium", "Low"):
            target = Severity.from_name(f)
            self._alerts = [a for a in self._alerts if a.severity == target]

        self.tree.delete(*self.tree.get_children())
        self._by_iid.clear()
        for a in self._alerts:
            iid = str(a.id)
            self._by_iid[iid] = a
            when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(a.timestamp))
            reason = (a.reasons[0] if a.reasons else "")[:70]
            status = a.resolution or ("ack" if a.acknowledged else "new")
            self.tree.insert("", "end", iid=iid,
                             values=(when, a.severity.label, a.process_name, a.pid,
                                     f"{a.risk_score:.0f}", reason, status),
                             tags=(a.severity.name,))

    # ------------------------------------------------------------------ #
    def _selected(self):
        sel = self.tree.selection()
        return self._by_iid.get(sel[0]) if sel else None

    def _show_detail(self, _e=None) -> None:
        a = self._selected()
        if not a:
            return
        lines = [
            f"{a.process_name}  (PID {a.pid})",
            f"Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(a.timestamp))}",
            f"Severity: {a.severity.label}    Risk: {a.risk_score:.0f}/100    "
            f"Confidence: {a.confidence:.0%}",
            f"Executable: {a.exe_path or 'unknown'}",
            f"User: {a.username or 'unknown'}",
            f"ML P(suspicious): {a.ml_probability:.0%}",
            "",
            "Reasons:",
        ]
        lines += [f"  - {r}" for r in a.reasons]
        lines += ["", "Rule hits: " + (", ".join(a.rule_hits) or "none")]
        lines += ["", "Recommended action:", f"  {a.recommended_action}"]
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", "\n".join(lines))
        self.detail.configure(state="disabled")

    def _acknowledge(self) -> None:
        a = self._selected()
        if a and a.id is not None:
            self.app.engine.db.acknowledge_alert(a.id, resolution="dismissed")
            from ...utils import audit
            audit.record("alert.acknowledge", {"id": a.id, "name": a.process_name})
            self._refresh()

    def _allowlist(self) -> None:
        a = self._selected()
        if not a:
            return
        pattern = a.exe_path or a.process_name
        self.app.engine.db.add_reputation("allow", pattern, note="from alert")
        if pattern not in self.app.settings.allowlist:
            self.app.settings.allowlist.append(pattern)
            self.app.settings.save()
        if a.id is not None:
            self.app.engine.db.acknowledge_alert(a.id, resolution="allowlisted")
        from ...utils import audit
        audit.record("reputation.allow.add", {"pattern": pattern})
        self._refresh()
