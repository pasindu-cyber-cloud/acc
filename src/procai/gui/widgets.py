"""Reusable CustomTkinter widgets for the ProcAI GUI.

Importing this module requires customtkinter; it is only imported from within the
running GUI. Widgets here are small composites (stat cards, badges, risk bars)
used across multiple pages.
"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from . import theme
from ..core.models import Severity


class StatCard(ctk.CTkFrame):
    """A compact metric card: a big value, a caption, optional accent colour."""

    def __init__(self, master, title: str, value: str = "-", *, accent: str = theme.PRIMARY,
                 subtitle: str = "", **kwargs):
        super().__init__(master, corner_radius=12, fg_color=theme.SURFACE, **kwargs)
        self.grid_columnconfigure(0, weight=1)

        self._accent_bar = ctk.CTkFrame(self, height=4, corner_radius=2, fg_color=accent)
        self._accent_bar.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 0))

        self._title = ctk.CTkLabel(self, text=title.upper(), font=theme.FONT_SMALL,
                                   text_color=theme.TEXT_MUTED)
        self._title.grid(row=1, column=0, sticky="w", padx=14, pady=(8, 0))

        self._value = ctk.CTkLabel(self, text=value, font=(theme.FONT_FAMILY, 28, "bold"),
                                   text_color=theme.TEXT)
        self._value.grid(row=2, column=0, sticky="w", padx=14, pady=(0, 2))

        self._subtitle = ctk.CTkLabel(self, text=subtitle, font=theme.FONT_SMALL,
                                      text_color=theme.TEXT_MUTED)
        self._subtitle.grid(row=3, column=0, sticky="w", padx=14, pady=(0, 12))

    def set(self, value: str, subtitle: Optional[str] = None, accent: Optional[str] = None):
        self._value.configure(text=value)
        if subtitle is not None:
            self._subtitle.configure(text=subtitle)
        if accent is not None:
            self._accent_bar.configure(fg_color=accent)


class SeverityBadge(ctk.CTkLabel):
    """A coloured pill showing a severity label."""

    def __init__(self, master, severity: Severity = Severity.INFO, **kwargs):
        super().__init__(master, text=f" {severity.label} ", corner_radius=10,
                         font=theme.FONT_SMALL, text_color="#0F1419",
                         fg_color=theme.severity_color(severity), **kwargs)

    def set_severity(self, severity: Severity):
        self.configure(text=f" {severity.label} ", fg_color=theme.severity_color(severity))


class RiskBar(ctk.CTkFrame):
    """A horizontal 0-100 risk meter with a numeric label."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self._bar = ctk.CTkProgressBar(self, height=14, corner_radius=7)
        self._bar.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._bar.set(0)
        self._label = ctk.CTkLabel(self, text="0", font=theme.FONT_SMALL, width=34)
        self._label.grid(row=0, column=1)

    def set_score(self, score: float):
        self._bar.set(max(0.0, min(1.0, score / 100.0)))
        self._bar.configure(progress_color=theme.risk_color(score))
        self._label.configure(text=f"{score:.0f}")


class SectionTitle(ctk.CTkLabel):
    def __init__(self, master, text: str, **kwargs):
        super().__init__(master, text=text, font=theme.FONT_HEADING,
                         text_color=theme.TEXT, anchor="w", **kwargs)


class Toast(ctk.CTkToplevel):
    """A small transient in-app notification window."""

    def __init__(self, master, title: str, message: str, severity: Severity = Severity.INFO):
        super().__init__(master)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(fg_color=theme.SURFACE_2)
        bar = ctk.CTkFrame(self, width=6, fg_color=theme.severity_color(severity))
        bar.pack(side="left", fill="y")
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(side="left", fill="both", expand=True, padx=12, pady=10)
        ctk.CTkLabel(body, text=title, font=theme.FONT_SUBHEADING, anchor="w").pack(fill="x")
        ctk.CTkLabel(body, text=message, font=theme.FONT_SMALL, anchor="w",
                     justify="left", wraplength=300, text_color=theme.TEXT_MUTED).pack(fill="x")
        self.after(100, self._place)
        self.after(6000, self.destroy)

    def _place(self):
        try:
            self.update_idletasks()
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            w, h = max(self.winfo_width(), 320), max(self.winfo_height(), 70)
            self.geometry(f"{w}x{h}+{sw - w - 24}+{sh - h - 60}")
        except Exception:
            pass


def confirm_dialog(master, title: str, message: str) -> bool:
    """Modal yes/no confirmation. Returns True if confirmed."""
    dialog = ctk.CTkInputDialog(text=f"{message}\n\nType YES to confirm:", title=title)
    return (dialog.get_input() or "").strip().upper() == "YES"
