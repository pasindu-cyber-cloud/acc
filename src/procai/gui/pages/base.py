"""Base class for all GUI pages.

Each page receives the shared application controller (which exposes the engine,
monitor, settings and helpers) and implements :meth:`build` once and
:meth:`on_show` for refresh-on-navigate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme

if TYPE_CHECKING:  # avoid import cycle at runtime
    from ..app import ProcAIApp


class BasePage(ctk.CTkFrame):
    """Common scaffolding: a title row plus a scrollable content area."""

    title: str = "Page"

    def __init__(self, master, app: "ProcAIApp"):
        super().__init__(master, fg_color=theme.BG)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 8))
        header.grid_columnconfigure(0, weight=1)
        self._title_label = ctk.CTkLabel(header, text=self.title, font=theme.FONT_TITLE,
                                         anchor="w")
        self._title_label.grid(row=0, column=0, sticky="w")
        self.header = header

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 20))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.build()

    # ------------------------------------------------------------------ #
    def build(self) -> None:
        """Construct widgets once. Override in subclasses."""

    def on_show(self) -> None:
        """Called every time the page becomes visible. Override to refresh."""
