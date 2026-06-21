"""Proc Assistant page: offline explanations + optional AI chat (privacy-gated)."""

from __future__ import annotations

import threading

import customtkinter as ctk

from .. import theme
import procai.assistant.ai_backends as ai_backends
from ...assistant.explain import explain_detection
from .base import BasePage


class AssistantPage(BasePage):
    title = "Proc Assistant"

    def build(self) -> None:
        c = self.content
        c.grid_rowconfigure(1, weight=1)
        c.grid_columnconfigure(0, weight=1)

        self.mode_label = ctk.CTkLabel(c, text="", font=theme.FONT_SMALL,
                                       text_color=theme.TEXT_MUTED, anchor="w")
        self.mode_label.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        self.chat = ctk.CTkTextbox(c, font=theme.FONT_BODY, wrap="word",
                                   fg_color=theme.SURFACE)
        self.chat.grid(row=1, column=0, sticky="nsew")
        self.chat.configure(state="disabled")

        row = ctk.CTkFrame(c, fg_color="transparent")
        row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        row.grid_columnconfigure(0, weight=1)
        self.entry = ctk.CTkEntry(row, placeholder_text="Ask about an alert, a PID, or your "
                                  "protection status...")
        self.entry.grid(row=0, column=0, sticky="ew")
        self.entry.bind("<Return>", lambda _e: self._send())
        ctk.CTkButton(row, text="Send", width=90, command=self._send).grid(
            row=0, column=1, padx=(8, 0))
        ctk.CTkButton(row, text="Explain latest alert", width=160, fg_color=theme.SURFACE_2,
                      hover_color="#2E3B49", command=self._explain_latest).grid(
            row=0, column=2, padx=(8, 0))

        self._last_context = ""

    # ------------------------------------------------------------------ #
    def on_show(self) -> None:
        status = ai_backends.backend_status(self.app.settings)
        if not status["assistant_enabled"]:
            self.mode_label.configure(
                text="Offline mode (deterministic, no network). Enable AI chat in Settings.")
        elif status["selected_backend"] == "ollama":
            self.mode_label.configure(text="AI chat: local Ollama (data stays on this machine).")
        elif status["selected_backend"] == "gemini":
            allowed = status["cloud_allowed"]
            self.mode_label.configure(
                text="AI chat: Gemini (cloud)." if allowed
                else "Gemini selected but blocked by privacy-first mode; using offline mode.")
        else:
            self.mode_label.configure(text="Offline mode.")

    # ------------------------------------------------------------------ #
    def _append(self, who: str, text: str) -> None:
        self.chat.configure(state="normal")
        self.chat.insert("end", f"\n[{who}]\n{text}\n")
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _explain_latest(self) -> None:
        alerts = self.app.engine.db.get_alerts(limit=1)
        if not alerts:
            self._append("Proc Assistant", "There are no alerts to explain yet.")
            return
        a = alerts[0]
        result = next((r for r in self.app.monitor.last_results
                       if r.snapshot.pid == a.pid), None)
        if result is not None:
            text = explain_detection(result)
            self._last_context = text
        else:
            text = (f"{a.process_name} (PID {a.pid}) - {a.severity.label} risk "
                    f"{a.risk_score:.0f}/100.\n" + "\n".join(f"- {r}" for r in a.reasons)
                    + f"\n\nRecommended: {a.recommended_action}")
            self._last_context = text
        self._append("Proc Assistant (offline)", text)

    def _send(self) -> None:
        q = self.entry.get().strip()
        if not q:
            return
        self.entry.delete(0, "end")
        self._append("You", q)
        status = ai_backends.backend_status(self.app.settings)

        if not status["assistant_enabled"] or self.app.settings.ai_backend == "offline":
            self._append("Proc Assistant (offline)", self._offline_answer(q))
            return

        # AI chat enabled -> run in a worker thread to keep the UI responsive.
        def work():
            try:
                answer = ai_backends.ask(self.app.settings, q, context=self._last_context)
            except ai_backends.AIUnavailable as exc:
                answer = f"(AI unavailable) {exc}\n\nFalling back to offline guidance:\n" \
                         + self._offline_answer(q)
            self.after(0, lambda: self._append("Proc Assistant", answer))

        threading.Thread(target=work, daemon=True).start()

    def _offline_answer(self, q: str) -> str:
        ql = q.lower()
        if "status" in ql or "protect" in ql:
            h = self.app.engine.health()
            return (f"Protection is {'active' if self.app.monitor.running else 'stopped'}. "
                    f"Model loaded: {h['model_loaded']}. Baselines: {h['baseline_identities']}. "
                    f"Sensitivity: {h['sensitivity']}.")
        if ql.strip().isdigit():
            result = self.app.engine.inspect(int(ql.strip()))
            if result:
                self._last_context = explain_detection(result)
                return self._last_context
            return f"I couldn't inspect PID {ql.strip()} (it may have exited)."
        return ("I'm in offline mode, so I can explain alerts and processes deterministically. "
                "Try 'explain latest alert', ask about 'status', or type a PID number. "
                "For free-form chat, enable the AI assistant in Settings.")
