"""Settings page: sensitivity, scanning, detection, notifications, privacy, lists."""

from __future__ import annotations

import threading

import customtkinter as ctk

from .. import theme
from ...config import SensitivityProfile, Settings
from .base import BasePage


class SettingsPage(BasePage):
    title = "Settings"

    def build(self) -> None:
        c = self.content
        c.grid_rowconfigure(0, weight=1)
        c.grid_columnconfigure(0, weight=1)
        scroll = ctk.CTkScrollableFrame(c, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        self._scroll = scroll

        self._build_monitoring(scroll)
        self._build_detection(scroll)
        self._build_notifications(scroll)
        self._build_privacy(scroll)
        self._build_lists(scroll)
        self._build_retention(scroll)

        actions = ctk.CTkFrame(c, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.save_status = ctk.CTkLabel(actions, text="", font=theme.FONT_SMALL,
                                        text_color=theme.SUCCESS)
        self.save_status.pack(side="left")
        ctk.CTkButton(actions, text="Save settings", width=140,
                      command=self._save).pack(side="right")

    # ------------------------------------------------------------------ #
    def _section(self, parent, title: str) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=theme.SURFACE, corner_radius=12)
        frame.grid(sticky="ew", pady=(0, 12))
        frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(frame, text=title, font=theme.FONT_SUBHEADING).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 6))
        return frame

    def _build_monitoring(self, parent) -> None:
        s = self.app.settings
        f = self._section(parent, "Monitoring")
        ctk.CTkLabel(f, text="Sensitivity profile").grid(row=1, column=0, sticky="w", padx=14)
        self.sensitivity = ctk.CTkOptionMenu(
            f, values=[p.value for p in SensitivityProfile], width=200)
        self.sensitivity.set(s.sensitivity.value)
        self.sensitivity.grid(row=1, column=1, sticky="w", padx=14, pady=4)

        ctk.CTkLabel(f, text="Scan interval (seconds)").grid(row=2, column=0, sticky="w", padx=14)
        self.scan_interval = ctk.CTkSlider(f, from_=1, to=30, number_of_steps=29)
        self.scan_interval.set(s.scan_interval_seconds)
        self.scan_interval.grid(row=2, column=1, sticky="ew", padx=14, pady=4)
        self.scan_label = ctk.CTkLabel(f, text=f"{s.scan_interval_seconds:.0f}s",
                                       text_color=theme.TEXT_MUTED)
        self.scan_label.grid(row=2, column=2, padx=8)
        self.scan_interval.configure(
            command=lambda v: self.scan_label.configure(text=f"{float(v):.0f}s"))

        self.learning = ctk.CTkSwitch(f, text="Learning mode (observe before getting strict)")
        if s.learning_mode:
            self.learning.select()
        self.learning.grid(row=3, column=0, columnspan=2, sticky="w", padx=14, pady=4)

        self.start_windows = ctk.CTkSwitch(f, text="Start with Windows (adds a visible startup entry)")
        if s.start_with_windows:
            self.start_windows.select()
        self.start_windows.grid(row=4, column=0, columnspan=2, sticky="w", padx=14, pady=4)

        self.tray_min = ctk.CTkSwitch(f, text="Minimise to system tray on close")
        if s.start_minimized_to_tray:
            self.tray_min.select()
        self.tray_min.grid(row=5, column=0, columnspan=2, sticky="w", padx=14, pady=(4, 12))

    def _build_detection(self, parent) -> None:
        s = self.app.settings
        f = self._section(parent, "Detection & machine learning")
        self.enable_ml = ctk.CTkSwitch(f, text="Use machine-learning model in the hybrid engine")
        if s.enable_ml:
            self.enable_ml.select()
        self.enable_ml.grid(row=1, column=0, columnspan=2, sticky="w", padx=14, pady=4)

        ctk.CTkLabel(f, text="Preferred model").grid(row=2, column=0, sticky="w", padx=14)
        self.model = ctk.CTkOptionMenu(f, values=["random_forest", "decision_tree"], width=200)
        self.model.set(s.preferred_model)
        self.model.grid(row=2, column=1, sticky="w", padx=14, pady=4)

        train = ctk.CTkFrame(f, fg_color="transparent")
        train.grid(row=3, column=0, columnspan=3, sticky="w", padx=10, pady=(4, 12))
        ctk.CTkButton(train, text="Train model on synthetic data", width=240,
                      command=self._train_synthetic).pack(side="left", padx=4)
        self.train_status = ctk.CTkLabel(train, text="", font=theme.FONT_SMALL,
                                         text_color=theme.TEXT_MUTED)
        self.train_status.pack(side="left", padx=8)

    def _build_notifications(self, parent) -> None:
        s = self.app.settings
        f = self._section(parent, "Notifications")
        self.notifications = ctk.CTkSwitch(f, text="Desktop notifications")
        if s.desktop_notifications:
            self.notifications.select()
        self.notifications.grid(row=1, column=0, columnspan=2, sticky="w", padx=14, pady=4)
        ctk.CTkLabel(f, text="Notify at minimum severity").grid(row=2, column=0, sticky="w",
                                                               padx=14)
        self.min_sev = ctk.CTkOptionMenu(
            f, values=["info", "low", "medium", "high", "critical"], width=160)
        self.min_sev.set(s.notify_min_severity)
        self.min_sev.grid(row=2, column=1, sticky="w", padx=14, pady=(4, 12))

    def _build_privacy(self, parent) -> None:
        s = self.app.settings
        f = self._section(parent, "Privacy & AI assistant")
        self.privacy = ctk.CTkSwitch(f, text="Privacy-first mode (block all cloud AI)")
        if s.privacy_first_mode:
            self.privacy.select()
        self.privacy.grid(row=1, column=0, columnspan=2, sticky="w", padx=14, pady=4)

        self.ai_enabled = ctk.CTkSwitch(f, text="Enable AI assistant chat (off by default)")
        if s.ai_assistant_enabled:
            self.ai_enabled.select()
        self.ai_enabled.grid(row=2, column=0, columnspan=2, sticky="w", padx=14, pady=4)

        ctk.CTkLabel(f, text="AI backend").grid(row=3, column=0, sticky="w", padx=14)
        self.ai_backend = ctk.CTkOptionMenu(f, values=["offline", "ollama", "gemini"], width=160)
        self.ai_backend.set(s.ai_backend)
        self.ai_backend.grid(row=3, column=1, sticky="w", padx=14, pady=4)

        ctk.CTkLabel(f, text="Ollama host").grid(row=4, column=0, sticky="w", padx=14)
        self.ollama_host = ctk.CTkEntry(f, width=260)
        self.ollama_host.insert(0, s.ai_ollama_host)
        self.ollama_host.grid(row=4, column=1, sticky="w", padx=14, pady=4)

        ctk.CTkLabel(f, text="Ollama model").grid(row=5, column=0, sticky="w", padx=14)
        self.ollama_model = ctk.CTkEntry(f, width=200)
        self.ollama_model.insert(0, s.ai_ollama_model)
        self.ollama_model.grid(row=5, column=1, sticky="w", padx=14, pady=4)

        ctk.CTkLabel(f, text="Gemini API key").grid(row=6, column=0, sticky="w", padx=14)
        self.gemini_key = ctk.CTkEntry(f, width=320, show="*")
        self.gemini_key.insert(0, s.ai_gemini_api_key)
        self.gemini_key.grid(row=6, column=1, sticky="w", padx=14, pady=(4, 12))

    def _build_lists(self, parent) -> None:
        f = self._section(parent, "Allowlist & blocklist")
        ctk.CTkLabel(f, text="Allowlist (trusted, alerts suppressed) - one per line").grid(
            row=1, column=0, columnspan=2, sticky="w", padx=14)
        self.allow_box = ctk.CTkTextbox(f, height=90, fg_color=theme.SURFACE_2)
        self.allow_box.insert("1.0", "\n".join(self.app.settings.allowlist))
        self.allow_box.grid(row=2, column=0, columnspan=2, sticky="ew", padx=14, pady=4)
        ctk.CTkLabel(f, text="Blocklist (always alert) - one per line").grid(
            row=3, column=0, columnspan=2, sticky="w", padx=14)
        self.block_box = ctk.CTkTextbox(f, height=90, fg_color=theme.SURFACE_2)
        self.block_box.insert("1.0", "\n".join(self.app.settings.blocklist))
        self.block_box.grid(row=4, column=0, columnspan=2, sticky="ew", padx=14, pady=(4, 12))

    def _build_retention(self, parent) -> None:
        s = self.app.settings
        f = self._section(parent, "Data retention")
        ctk.CTkLabel(f, text="Process history retention (days)").grid(row=1, column=0,
                                                                      sticky="w", padx=14)
        self.hist_days = ctk.CTkEntry(f, width=80)
        self.hist_days.insert(0, str(s.process_history_retention_days))
        self.hist_days.grid(row=1, column=1, sticky="w", padx=14, pady=4)
        ctk.CTkLabel(f, text="Log/alert retention (days)").grid(row=2, column=0, sticky="w",
                                                               padx=14)
        self.log_days = ctk.CTkEntry(f, width=80)
        self.log_days.insert(0, str(s.log_retention_days))
        self.log_days.grid(row=2, column=1, sticky="w", padx=14, pady=(4, 12))

    # ------------------------------------------------------------------ #
    def on_show(self) -> None:
        pass

    def _train_synthetic(self) -> None:
        from ...core.ml import ml_available

        if not ml_available():
            self.train_status.configure(
                text="scikit-learn not installed (pip install procai[ml]).",
                text_color=theme.WARNING)
            return
        self.train_status.configure(text="Training...", text_color=theme.TEXT_MUTED)

        def work():
            from ...core import simulation
            from ...core.ml import train_and_save

            try:
                data = simulation.generate_training_data()
                md = train_and_save(self.model.get(), data)
                msg = (f"Trained {md.algorithm}: acc {md.accuracy:.0%}, "
                       f"F1 {md.f1:.0%} on {md.n_samples} samples.")
                self.app.engine.db.upsert_model_metadata(md)
                color = theme.SUCCESS
            except Exception as exc:  # pragma: no cover
                msg, color = f"Training failed: {exc}", theme.WARNING
            self.after(0, lambda: self.train_status.configure(text=msg, text_color=color))

        threading.Thread(target=work, daemon=True).start()

    def _save(self) -> None:
        s = self.app.settings
        new = Settings.from_dict(s.to_dict())  # start from current to keep consent etc.
        new.sensitivity = SensitivityProfile(self.sensitivity.get())
        new.scan_interval_seconds = float(self.scan_interval.get())
        new.learning_mode = bool(self.learning.get())
        new.start_with_windows = bool(self.start_windows.get())
        new.start_minimized_to_tray = bool(self.tray_min.get())
        new.enable_ml = bool(self.enable_ml.get())
        new.preferred_model = self.model.get()
        new.desktop_notifications = bool(self.notifications.get())
        new.notify_min_severity = self.min_sev.get()
        new.privacy_first_mode = bool(self.privacy.get())
        new.ai_assistant_enabled = bool(self.ai_enabled.get())
        new.ai_backend = self.ai_backend.get()
        new.ai_ollama_host = self.ollama_host.get().strip()
        new.ai_ollama_model = self.ollama_model.get().strip()
        new.ai_gemini_api_key = self.gemini_key.get().strip()
        new.allowlist = [x.strip() for x in self.allow_box.get("1.0", "end").splitlines()
                         if x.strip()]
        new.blocklist = [x.strip() for x in self.block_box.get("1.0", "end").splitlines()
                         if x.strip()]
        try:
            new.process_history_retention_days = int(self.hist_days.get())
            new.log_retention_days = int(self.log_days.get())
        except ValueError:
            pass

        # Apply Windows startup change (visible, user-requested) if it changed.
        if new.start_with_windows != s.start_with_windows:
            self._apply_startup(new.start_with_windows)

        self.app.apply_settings(new)
        self.save_status.configure(text="Settings saved.", text_color=theme.SUCCESS)

    def _apply_startup(self, enable: bool) -> None:
        try:
            from ...service.autostart import set_autostart

            set_autostart(enable)
        except Exception as exc:  # pragma: no cover
            self.save_status.configure(text=f"(startup change skipped: {exc})",
                                       text_color=theme.WARNING)
