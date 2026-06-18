"""Execution mode capabilities.

  analytics : observe + score only. No positions of any kind.
  paper     : simulate positions locally on the live/replay feed. No orders.
  demo      : place REAL orders on a Deriv DEMO account (token required).
  live      : place REAL orders on a Deriv REAL account (token + explicit confirm).

`places_real_orders` is the single source of truth used to decide whether an
ExecutionGateway is even constructed.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..constants import Mode


@dataclass(frozen=True)
class ModeCapabilities:
    mode: Mode
    simulates_positions: bool
    places_real_orders: bool
    requires_token: bool
    requires_live_confirm: bool


_CAPS = {
    Mode.ANALYTICS: ModeCapabilities(Mode.ANALYTICS, False, False, False, False),
    Mode.PAPER: ModeCapabilities(Mode.PAPER, True, False, False, False),
    Mode.DEMO: ModeCapabilities(Mode.DEMO, True, True, True, False),
    Mode.LIVE: ModeCapabilities(Mode.LIVE, True, True, True, True),
}


def capabilities(mode: Mode) -> ModeCapabilities:
    return _CAPS[mode]
