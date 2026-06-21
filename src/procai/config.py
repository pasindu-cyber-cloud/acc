"""Configuration, filesystem paths, and user settings for ProcAI.

This module centralises every on-disk location ProcAI uses and the user-tunable
settings model. Paths follow platform conventions:

* Windows  -> %LOCALAPPDATA%\\ProcAI  and  %PROGRAMDATA%\\ProcAI
* Linux    -> ~/.local/share/procai   (useful for development/testing)
* macOS    -> ~/Library/Application Support/ProcAI

Design notes
------------
* Settings are a plain dataclass that serialises to/from JSON. The database also
  stores a copy so the background service and GUI share one source of truth, but
  a JSON fallback keeps ProcAI usable even before the DB is initialised.
* Everything here is privacy-first: AI assistant network access defaults OFF and
  must be explicitly enabled by the user.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any

from . import APP_NAME

# --------------------------------------------------------------------------- #
# Filesystem layout
# --------------------------------------------------------------------------- #


def _base_data_dir() -> Path:
    """Return the per-user writable data directory for ProcAI."""
    override = os.environ.get("PROCAI_DATA_DIR")
    if override:
        return Path(override)

    if sys.platform.startswith("win"):
        root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        return Path(root) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "procai"


@dataclass(frozen=True)
class Paths:
    """Resolved filesystem paths. Created lazily via :meth:`ensure`."""

    data_dir: Path
    db_path: Path
    logs_dir: Path
    models_dir: Path
    reports_dir: Path
    settings_path: Path
    audit_path: Path

    @classmethod
    def resolve(cls) -> "Paths":
        base = _base_data_dir()
        return cls(
            data_dir=base,
            db_path=base / "procai.db",
            logs_dir=base / "logs",
            models_dir=base / "models",
            reports_dir=base / "reports",
            settings_path=base / "settings.json",
            audit_path=base / "logs" / "audit.log",
        )

    def ensure(self) -> "Paths":
        """Create all directories. Safe to call repeatedly."""
        for d in (self.data_dir, self.logs_dir, self.models_dir, self.reports_dir):
            d.mkdir(parents=True, exist_ok=True)
        return self


PATHS = Paths.resolve()


# --------------------------------------------------------------------------- #
# Sensitivity profiles
# --------------------------------------------------------------------------- #


class SensitivityProfile(str, Enum):
    """How aggressively ProcAI raises alerts.

    The profile scales the alert threshold and the relative weight of ML vs.
    rules. ``RESEARCH`` is the most verbose (lowest threshold) and is intended
    for lab/testing so the full pipeline is observable.
    """

    LOW = "low"
    BALANCED = "balanced"
    STRICT = "strict"
    RESEARCH = "research"

    @property
    def alert_threshold(self) -> float:
        """Final risk score (0-100) at/above which an alert is raised."""
        return {
            SensitivityProfile.LOW: 75.0,
            SensitivityProfile.BALANCED: 60.0,
            SensitivityProfile.STRICT: 45.0,
            SensitivityProfile.RESEARCH: 30.0,
        }[self]

    @property
    def ml_weight(self) -> float:
        """Weight given to the ML component in the hybrid fusion (0-1)."""
        return {
            SensitivityProfile.LOW: 0.35,
            SensitivityProfile.BALANCED: 0.45,
            SensitivityProfile.STRICT: 0.55,
            SensitivityProfile.RESEARCH: 0.50,
        }[self]


# --------------------------------------------------------------------------- #
# Settings model
# --------------------------------------------------------------------------- #


@dataclass
class Settings:
    """User-tunable settings. Serialises to JSON and mirrors into the DB."""

    # --- Monitoring ---
    sensitivity: SensitivityProfile = SensitivityProfile.BALANCED
    scan_interval_seconds: float = 3.0
    learning_mode: bool = True
    learning_duration_minutes: int = 30
    start_with_windows: bool = False
    start_minimized_to_tray: bool = True

    # --- Detection ---
    enable_ml: bool = True
    preferred_model: str = "random_forest"  # or "decision_tree"
    baseline_min_samples: int = 8
    suppress_trusted: bool = True

    # --- Notifications ---
    desktop_notifications: bool = True
    notify_min_severity: str = "high"  # info|low|medium|high|critical

    # --- Privacy / AI assistant (OFF by default) ---
    privacy_first_mode: bool = True
    ai_assistant_enabled: bool = False
    ai_backend: str = "offline"  # offline|gemini|ollama
    ai_gemini_api_key: str = ""
    ai_ollama_host: str = "http://localhost:11434"
    ai_ollama_model: str = "llama3"

    # --- Retention / logging ---
    log_retention_days: int = 30
    process_history_retention_days: int = 14
    audit_enabled: bool = True

    # --- Lists ---
    allowlist: list[str] = field(default_factory=list)  # process names or exe paths
    blocklist: list[str] = field(default_factory=list)

    # --- Consent / state ---
    consent_accepted: bool = False
    consent_version: str = "1.0"

    # ------------------------------------------------------------------ #
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["sensitivity"] = self.sensitivity.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        data = dict(data)
        if "sensitivity" in data and not isinstance(data["sensitivity"], SensitivityProfile):
            try:
                data["sensitivity"] = SensitivityProfile(data["sensitivity"])
            except ValueError:
                data["sensitivity"] = SensitivityProfile.BALANCED
        # Drop unknown keys so old config files load forward-compatibly.
        valid = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid})

    # ------------------------------------------------------------------ #
    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or PATHS.settings_path
        if path.exists():
            try:
                return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError, TypeError):
                # Corrupt settings should never crash the app; fall back to defaults.
                return cls()
        return cls()

    def save(self, path: Path | None = None) -> None:
        path = path or PATHS.settings_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")


# Directories commonly considered higher-risk locations for executables to run
# from on Windows. Used by the reputation/rules modules (advisory only).
SUSPICIOUS_DIR_HINTS: tuple[str, ...] = (
    r"\appdata\local\temp",
    r"\windows\temp",
    r"\users\public",
    r"\programdata\temp",
    r"\downloads",
    r"\recycle.bin",
    r"\$recycle.bin",
    r"\appdata\roaming\temp",
    "/tmp/",
    "/dev/shm/",
)

# Consent text shown on first run / in the installer.
CONSENT_VERSION = "1.0"
