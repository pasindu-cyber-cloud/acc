"""Configuration loading and validation (stdlib + PyYAML-optional).

Resolution order (lowest -> highest priority):
  1. config/default.yaml          (research defaults, committed)
  2. config/risk_profiles.yaml    (per-profile overrides)
  3. environment variables / .env (deployment specifics & secrets)
  4. explicit overrides passed in code/CLI

Secrets (API token) come ONLY from the environment, never from YAML.

PyYAML is used if installed; otherwise a tiny built-in loader handles the
project's own (simple) YAML config files so the system runs with zero deps.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .constants import (
    DEFAULT_APP_ID,
    DEFAULT_WS_URL,
    LIVE_CONFIRM_TOKEN,
    DataSource,
    Mode,
    RiskProfileName,
)
from .yaml_lite import load_yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return load_yaml(path.read_text(encoding="utf-8")) or {}


@dataclass
class DerivSettings:
    app_id: str = DEFAULT_APP_ID
    ws_url: str = DEFAULT_WS_URL
    api_token: str | None = None
    currency: str = "USD"


@dataclass
class RiskProfile:
    name: str
    description: str = ""
    ready_threshold: float = 72.0
    min_ready_persistence_ticks: int = 15
    max_growth_rate: float = 0.03
    stability_floor: float = 60.0
    jump_safety_floor: float = 65.0
    allow_high_vol_families: bool = False
    preferred_families: list[str] = field(default_factory=list)
    safeguards: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, name: str, d: dict[str, Any]) -> "RiskProfile":
        return cls(
            name=name,
            description=d.get("description", ""),
            ready_threshold=float(d.get("ready_threshold", 72.0)),
            min_ready_persistence_ticks=int(d.get("min_ready_persistence_ticks", 15)),
            max_growth_rate=float(d.get("max_growth_rate", 0.03)),
            stability_floor=float(d.get("stability_floor", 60.0)),
            jump_safety_floor=float(d.get("jump_safety_floor", 65.0)),
            allow_high_vol_families=bool(d.get("allow_high_vol_families", False)),
            preferred_families=list(d.get("preferred_families", [])),
            safeguards=dict(d.get("safeguards", {})),
        )


@dataclass
class AppConfig:
    mode: Mode = Mode.ANALYTICS
    data_source: DataSource = DataSource.MOCK
    live_confirmed: bool = False
    symbols: list[str] = field(default_factory=list)
    db_url: str = "sqlite:///storage/accuscan.db"
    log_level: str = "INFO"
    deriv: DerivSettings = field(default_factory=DerivSettings)
    risk_profile: RiskProfile = field(default_factory=lambda: RiskProfile(name="conservative"))
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8000
    raw: dict[str, Any] = field(default_factory=dict)

    def section(self, name: str) -> dict[str, Any]:
        return dict(self.raw.get(name, {}))


def _env(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name, default)
    if val is not None and val.strip() == "":
        return default
    return val


def load_config(
    *,
    mode: str | None = None,
    risk_profile: str | None = None,
    data_source: str | None = None,
    symbols: list[str] | None = None,
) -> AppConfig:
    defaults = _load_yaml(CONFIG_DIR / "default.yaml")
    profiles = _load_yaml(CONFIG_DIR / "risk_profiles.yaml")

    profile_name = (
        risk_profile or _env("ACCUSCAN_RISK_PROFILE") or RiskProfileName.CONSERVATIVE.value
    ).lower()
    profile_raw = profiles.get(profile_name, profiles.get("conservative", {}))
    profile = RiskProfile.from_dict(profile_name, profile_raw)

    mode_str = (mode or _env("ACCUSCAN_MODE") or Mode.ANALYTICS.value).lower()
    resolved_mode = Mode(mode_str)
    live_confirm = _env("ACCUSCAN_LIVE_CONFIRM") == LIVE_CONFIRM_TOKEN

    ds_str = (data_source or _env("ACCUSCAN_DATA_SOURCE") or DataSource.MOCK.value).lower()
    resolved_ds = DataSource(ds_str)

    sym_list = symbols
    if sym_list is None:
        sym_env = _env("ACCUSCAN_SYMBOLS")
        sym_list = [s.strip() for s in sym_env.split(",")] if sym_env else []

    deriv = DerivSettings(
        app_id=_env("DERIV_APP_ID", DEFAULT_APP_ID) or DEFAULT_APP_ID,
        ws_url=_env("DERIV_WS_URL", DEFAULT_WS_URL) or DEFAULT_WS_URL,
        api_token=_env("DERIV_API_TOKEN"),
        currency=_env("DERIV_CURRENCY", "USD") or "USD",
    )

    merged = dict(defaults)
    if "scoring" in merged and isinstance(merged["scoring"], dict):
        merged["scoring"]["min_ready_persistence_ticks"] = profile.min_ready_persistence_ticks

    return AppConfig(
        mode=resolved_mode,
        data_source=resolved_ds,
        live_confirmed=live_confirm,
        symbols=sym_list,
        db_url=_env("ACCUSCAN_DB_URL", "sqlite:///storage/accuscan.db") or "sqlite:///storage/accuscan.db",
        log_level=_env("ACCUSCAN_LOG_LEVEL", "INFO") or "INFO",
        deriv=deriv,
        risk_profile=profile,
        dashboard_host=_env("ACCUSCAN_DASHBOARD_HOST", "127.0.0.1") or "127.0.0.1",
        dashboard_port=int(_env("ACCUSCAN_DASHBOARD_PORT", "8000") or "8000"),
        raw=merged,
    )


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return load_config()


def validate_execution_allowed(cfg: AppConfig) -> tuple[bool, str]:
    """Gate deciding whether the requested mode may actually place orders."""
    if cfg.mode in (Mode.ANALYTICS, Mode.PAPER):
        return True, ""
    if cfg.deriv.api_token is None:
        return False, f"{cfg.mode.value} mode requires DERIV_API_TOKEN."
    if cfg.mode is Mode.LIVE and not cfg.live_confirmed:
        return (
            False,
            f"Live mode requires ACCUSCAN_LIVE_CONFIRM={LIVE_CONFIRM_TOKEN} to be set.",
        )
    return True, ""
