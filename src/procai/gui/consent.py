"""First-run consent dialog.

ProcAI is transparent software: before any monitoring begins the user is shown
exactly what it does, what it reads, and the guarantees it makes (no stealth, no
disabling of Windows Defender, privacy-first by default). Monitoring only starts
after explicit acceptance.
"""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from . import theme

CONSENT_TEXT = (
    "ProcAI is a defensive endpoint-monitoring tool. Before it starts, please "
    "review what it does:\n\n"
    "WHAT PROCAI DOES\n"
    "  - Reads the list of running processes and their resource usage (CPU, memory, "
    "threads, network connections, executable path, parent process).\n"
    "  - Builds a local baseline of normal behaviour and flags unusual activity using "
    "transparent rules, statistics and an optional local machine-learning model.\n"
    "  - Stores alerts, history and settings in a local database on THIS machine only.\n\n"
    "WHAT PROCAI WILL NOT DO\n"
    "  - It will not hide itself; a tray icon and dashboard are always available.\n"
    "  - It will not disable or modify Windows Defender or any antivirus.\n"
    "  - It will not send your data anywhere. The optional AI assistant is OFF by "
    "default and only contacts a cloud service if you explicitly enable it and turn "
    "off privacy-first mode.\n"
    "  - It will never terminate a process without your explicit confirmation.\n\n"
    "You can stop monitoring, change settings, export your data, or uninstall ProcAI "
    "at any time. By accepting you consent to local process monitoring as described."
)


class ConsentDialog(ctk.CTkToplevel):
    def __init__(self, master, *, on_accept: Callable[[], None], on_decline: Callable[[], None]):
        super().__init__(master)
        self.on_accept = on_accept
        self.on_decline = on_decline

        self.title("Welcome to ProcAI - Consent & Transparency")
        self.geometry("640x620")
        self.configure(fg_color=theme.BG)
        self.grab_set()  # modal
        self.protocol("WM_DELETE_WINDOW", self._decline)

        ctk.CTkLabel(self, text="\U0001F6E1  Welcome to ProcAI",
                     font=theme.FONT_TITLE).pack(anchor="w", padx=24, pady=(22, 4))
        ctk.CTkLabel(self, text="Transparent, defensive process monitoring",
                     font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED).pack(
            anchor="w", padx=24)

        box = ctk.CTkTextbox(self, font=theme.FONT_BODY, fg_color=theme.SURFACE,
                             wrap="word", corner_radius=10)
        box.pack(fill="both", expand=True, padx=24, pady=16)
        box.insert("1.0", CONSENT_TEXT)
        box.configure(state="disabled")

        self._agree = ctk.CTkCheckBox(
            self, text="I understand and consent to local process monitoring.",
            font=theme.FONT_BODY, command=self._toggle)
        self._agree.pack(anchor="w", padx=24, pady=(0, 8))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=(0, 20))
        ctk.CTkButton(row, text="Decline & Exit", fg_color=theme.SURFACE_2,
                      hover_color="#2E3B49", command=self._decline).pack(side="left")
        self._accept_btn = ctk.CTkButton(row, text="Accept & Continue", state="disabled",
                                         command=self._accept)
        self._accept_btn.pack(side="right")

    def _toggle(self) -> None:
        self._accept_btn.configure(state="normal" if self._agree.get() else "disabled")

    def _accept(self) -> None:
        self.grab_release()
        self.destroy()
        self.on_accept()

    def _decline(self) -> None:
        self.grab_release()
        self.destroy()
        self.on_decline()
