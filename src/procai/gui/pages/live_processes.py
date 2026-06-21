"""Live Processes: a sortable, searchable table of the latest scan results."""

from __future__ import annotations

from tkinter import ttk

import customtkinter as ctk

from .. import theme
from ...core.models import Severity
from .base import BasePage

_COLUMNS = [
    ("pid", "PID", 70),
    ("name", "Process", 190),
    ("user", "User", 130),
    ("cpu", "CPU %", 70),
    ("mem", "Mem MB", 80),
    ("threads", "Threads", 70),
    ("net", "Conns", 60),
    ("risk", "Risk", 60),
    ("severity", "Severity", 90),
    ("signed", "Signed", 70),
    ("path", "Executable Path", 360),
]


def style_treeview() -> ttk.Style:
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure(
        "ProcAI.Treeview", background=theme.SURFACE, fieldbackground=theme.SURFACE,
        foreground=theme.TEXT, rowheight=26, borderwidth=0, font=("Segoe UI", 10))
    style.configure(
        "ProcAI.Treeview.Heading", background=theme.SURFACE_2, foreground=theme.TEXT,
        relief="flat", font=("Segoe UI", 10, "bold"))
    style.map("ProcAI.Treeview", background=[("selected", theme.PRIMARY_DARK)])
    return style


class LiveProcessesPage(BasePage):
    title = "Live Processes"

    def build(self) -> None:
        style_treeview()
        c = self.content
        c.grid_rowconfigure(1, weight=1)

        # Toolbar
        bar = ctk.CTkFrame(c, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        bar.grid_columnconfigure(1, weight=1)
        self.search = ctk.CTkEntry(bar, placeholder_text="Search process name / path / user...",
                                   width=320)
        self.search.grid(row=0, column=0, sticky="w")
        self.search.bind("<KeyRelease>", lambda _e: self._refresh())
        self.count_label = ctk.CTkLabel(bar, text="", text_color=theme.TEXT_MUTED,
                                        font=theme.FONT_SMALL)
        self.count_label.grid(row=0, column=1, sticky="w", padx=12)
        ctk.CTkButton(bar, text="Refresh", width=90, command=self._scan_now).grid(
            row=0, column=2, padx=(0, 6))
        ctk.CTkButton(bar, text="Simulate", width=90, fg_color=theme.SURFACE_2,
                      hover_color="#2E3B49", command=self._simulate).grid(row=0, column=3)

        # Table
        wrap = ctk.CTkFrame(c, fg_color=theme.SURFACE, corner_radius=12)
        wrap.grid(row=1, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(0, weight=1)
        cols = [c[0] for c in _COLUMNS]
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", style="ProcAI.Treeview")
        for key, label, width in _COLUMNS:
            self.tree.heading(key, text=label,
                              command=lambda k=key: self._sort_by(k))
            self.tree.column(key, width=width, anchor="w")
        for sev in Severity:
            self.tree.tag_configure(sev.name, foreground=theme.severity_color(sev))
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        vsb.grid(row=0, column=1, sticky="ns", pady=8, padx=(0, 8))
        self.tree.bind("<Double-1>", self._open_intelligence)

        self._sort_key = "risk"
        self._sort_desc = True
        self._results = []

    # ------------------------------------------------------------------ #
    def _scan_now(self) -> None:
        self._results = self.app.engine.scan_once()
        self._refresh()

    def _simulate(self) -> None:
        import procai.core.simulation as simulation

        snaps = simulation.generate()
        self._results = self.app.engine.scan_once(snaps, enrich_reputation=False)
        self._refresh()

    def on_show(self) -> None:
        latest = self.app.monitor.last_results
        if latest:
            self._results = latest
        elif not self._results:
            self._scan_now()
        self._refresh()

    # ------------------------------------------------------------------ #
    def _sort_by(self, key: str) -> None:
        if self._sort_key == key:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_key = key
            self._sort_desc = True
        self._refresh()

    def _filtered_sorted(self):
        q = (self.search.get() or "").strip().lower()
        rows = self._results
        if q:
            rows = [r for r in rows if q in r.snapshot.name.lower()
                    or q in (r.snapshot.exe_path or "").lower()
                    or q in (r.snapshot.username or "").lower()]
        keymap = {
            "pid": lambda r: r.snapshot.pid, "name": lambda r: r.snapshot.name.lower(),
            "user": lambda r: r.snapshot.username.lower(), "cpu": lambda r: r.snapshot.cpu_percent,
            "mem": lambda r: r.snapshot.memory_mb, "threads": lambda r: r.snapshot.num_threads,
            "net": lambda r: r.snapshot.num_connections, "risk": lambda r: r.risk_score,
            "severity": lambda r: int(r.severity), "signed": lambda r: str(r.snapshot.is_signed),
            "path": lambda r: (r.snapshot.exe_path or "").lower(),
        }
        kf = keymap.get(self._sort_key, lambda r: r.risk_score)
        return sorted(rows, key=kf, reverse=self._sort_desc)

    def _refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        rows = self._filtered_sorted()
        for r in rows:
            s = r.snapshot
            signed = "Yes" if s.is_signed else ("No" if s.is_signed is False else "?")
            self.tree.insert(
                "", "end", iid=str(s.pid),
                values=(s.pid, s.name, s.username, f"{s.cpu_percent:.0f}",
                        f"{s.memory_mb:.0f}", s.num_threads, s.num_connections,
                        f"{r.risk_score:.0f}", r.severity.label, signed, s.exe_path),
                tags=(r.severity.name,))
        self.count_label.configure(text=f"{len(rows)} processes shown")

    def _open_intelligence(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        try:
            pid = int(sel[0])
        except ValueError:
            return
        self.app.show_page("intelligence")
        page = self.app._pages.get("intelligence")
        if page:
            page.inspect_pid(pid)
