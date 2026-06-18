"""Offline synthetic market-data source.

Generates realistic-enough synthetic-index ticks so the full pipeline
(scanner -> features -> scoring -> deterioration -> alerts -> paper trading)
can run and be tested with NO network access.

The generator models distinct *regimes* per symbol so that deterioration and
alerting can be exercised:
  - CALM:     small gaussian increments, range-bound (good for accumulators)
  - TRENDING: drift + moderate noise
  - VOLATILE: larger increments, occasional bursts
  - JUMPY:    calm baseline punctuated by rare large jumps (worst for ACCU)

This is a substitute for live data only; it is NOT a market model for trading.
"""

from __future__ import annotations

import asyncio
import math
import random
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from ..constants import ALLOWED_GROWTH_RATES
from ..models import SymbolInfo, Tick
from .base import MarketDataSource

REGIMES = ("CALM", "TRENDING", "VOLATILE", "JUMPY")


@dataclass
class _SymbolState:
    symbol: str
    price: float
    pip_size: int
    regime: str
    step_sigma: float          # base increment std in price units
    drift: float = 0.0
    jump_rate: float = 0.0     # prob per tick of a jump
    jump_size: float = 0.0
    regime_ticks_left: int = 0
    rng: random.Random = field(default_factory=random.Random)

    def next_quote(self) -> float:
        # Occasional regime switch to drive deterioration scenarios.
        if self.regime_ticks_left <= 0:
            self._switch_regime()
        self.regime_ticks_left -= 1

        increment = self.rng.gauss(self.drift, self.step_sigma)
        if self.jump_rate and self.rng.random() < self.jump_rate:
            increment += self.rng.choice((-1.0, 1.0)) * self.jump_size
        self.price = max(self.price + increment, 10 ** (-self.pip_size))
        return round(self.price, self.pip_size)

    def _switch_regime(self) -> None:
        self.regime = self.rng.choices(
            REGIMES, weights=[0.45, 0.25, 0.20, 0.10], k=1
        )[0]
        self.regime_ticks_left = self.rng.randint(60, 240)
        base = self.step_sigma
        if self.regime == "CALM":
            self.drift, self.jump_rate, self.jump_size = 0.0, 0.0, 0.0
            self._active_sigma = base * 0.6
        elif self.regime == "TRENDING":
            self.drift = self.rng.choice((-1, 1)) * base * 0.4
            self.jump_rate, self.jump_size = 0.0, 0.0
            self._active_sigma = base
        elif self.regime == "VOLATILE":
            self.drift, self.jump_rate, self.jump_size = 0.0, 0.02, base * 6
            self._active_sigma = base * 2.2
        else:  # JUMPY
            self.drift, self.jump_rate, self.jump_size = 0.0, 0.06, base * 14
            self._active_sigma = base * 0.8
        # apply active sigma
        self._base_sigma = base
        object.__setattr__(self, "step_sigma_runtime", self._active_sigma)
        self.step_sigma = self._active_sigma


# Default offline universe mirroring Deriv synthetic families.
_DEFAULT_UNIVERSE = {
    "R_10": (0.04, 5),
    "R_25": (0.10, 4),
    "R_50": (0.20, 4),
    "R_75": (0.30, 4),
    "R_100": (0.40, 2),
    "1HZ10V": (0.04, 4),
    "1HZ25V": (0.10, 4),
    "1HZ50V": (0.20, 4),
    "1HZ100V": (0.40, 2),
}


class MockDataSource(MarketDataSource):
    def __init__(
        self,
        symbols: list[str] | None = None,
        tick_interval: float = 0.2,
        seed: int = 7,
    ) -> None:
        self.tick_interval = tick_interval
        self._rng = random.Random(seed)
        chosen = symbols or list(_DEFAULT_UNIVERSE.keys())
        self._states: dict[str, _SymbolState] = {}
        for i, sym in enumerate(chosen):
            sigma, pip = _DEFAULT_UNIVERSE.get(sym, (0.10, 4))
            st = _SymbolState(
                symbol=sym,
                price=1000.0 + i * 13.7,
                pip_size=pip,
                regime="CALM",
                step_sigma=sigma,
                rng=random.Random(seed + i * 101),
            )
            st._switch_regime()
            self._states[sym] = st
        self._connected = False

    async def connect(self) -> None:
        self._connected = True

    async def close(self) -> None:
        self._connected = False

    async def list_symbols(self) -> list[SymbolInfo]:
        out = []
        for sym, st in self._states.items():
            out.append(
                SymbolInfo(
                    symbol=sym,
                    display_name=sym,
                    pip_size=st.pip_size,
                    accu_available=True,
                    allowed_growth_rates=list(ALLOWED_GROWTH_RATES),
                    family=_family(sym),
                )
            )
        return out

    async def history(self, symbol: str, count: int) -> list[Tick]:
        st = self._states[symbol]
        now = int(time.time()) - count
        ticks: list[Tick] = []
        for i in range(count):
            q = st.next_quote()
            ticks.append(
                Tick(symbol=symbol, epoch=now + i, quote=q, pip_size=st.pip_size, recv_ts=time.time())
            )
        return ticks

    async def subscribe(self, symbols: list[str]) -> AsyncIterator[Tick]:
        async def _gen() -> AsyncIterator[Tick]:
            epoch = int(time.time())
            while self._connected:
                epoch += 1
                # Emit one tick per symbol per cycle (round-robin).
                for sym in symbols:
                    st = self._states[sym]
                    q = st.next_quote()
                    yield Tick(
                        symbol=sym,
                        epoch=epoch,
                        quote=q,
                        pip_size=st.pip_size,
                        recv_ts=time.time(),
                    )
                await asyncio.sleep(self.tick_interval)

        return _gen()

    async def ping(self) -> float:
        # Simulate a tiny, slightly jittery latency.
        return 5.0 + self._rng.random() * 10.0


def _family(symbol: str) -> str:
    for prefix in ("1HZ", "R_", "BOOM", "CRASH", "JD", "stpRNG"):
        if symbol.startswith(prefix):
            return prefix
    return symbol


def deterministic_series(
    n: int,
    *,
    regime: str = "CALM",
    sigma: float = 0.1,
    pip_size: int = 4,
    seed: int = 0,
    start: float = 1000.0,
) -> list[float]:
    """Helper used by tests/backtests to build a reproducible price path."""
    rng = random.Random(seed)
    price = start
    out = []
    for i in range(n):
        inc = rng.gauss(0.0, sigma)
        if regime == "JUMPY" and rng.random() < 0.05:
            inc += rng.choice((-1, 1)) * sigma * 14
        elif regime == "VOLATILE":
            inc *= 2.2
        elif regime == "TRENDING":
            inc += sigma * 0.4
        price = max(price + inc, 10 ** (-pip_size))
        out.append(round(price, pip_size))
    return out
