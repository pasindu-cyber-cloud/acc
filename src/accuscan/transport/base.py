"""Abstract transport interfaces.

Two responsibilities are separated:
  - MarketDataSource: public market data only (no auth required).
  - ExecutionGateway: authenticated order placement (demo/live).

Keeping them apart enforces the safety property that the scanner/analytics
path can NEVER place an order, because it is only ever handed a
MarketDataSource.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator

from ..models import OpenContract, Proposal, SymbolInfo, Tick


class MarketDataSource(abc.ABC):
    """Read-only market data feed."""

    @abc.abstractmethod
    async def connect(self) -> None: ...

    @abc.abstractmethod
    async def close(self) -> None: ...

    @abc.abstractmethod
    async def list_symbols(self) -> list[SymbolInfo]:
        """active_symbols + contracts_for screening -> ACCU-eligible symbols."""

    @abc.abstractmethod
    async def history(self, symbol: str, count: int) -> list[Tick]:
        """ticks_history seed for a symbol."""

    @abc.abstractmethod
    def subscribe(self, symbols: list[str]) -> AsyncIterator[Tick]:
        """Async stream of live ticks for the given symbols."""

    @abc.abstractmethod
    async def ping(self) -> float:
        """Round-trip latency in milliseconds (health check)."""


class ExecutionGateway(abc.ABC):
    """Authenticated execution. Only constructed when mode in {demo, live}."""

    @abc.abstractmethod
    async def connect(self) -> None: ...

    @abc.abstractmethod
    async def close(self) -> None: ...

    @abc.abstractmethod
    async def authorize(self, token: str) -> dict: ...

    @abc.abstractmethod
    async def propose(self, proposal: Proposal) -> Proposal:
        """Call `proposal` and return it enriched with id/spot."""

    @abc.abstractmethod
    async def buy(self, proposal_id: str, price: float) -> OpenContract: ...

    @abc.abstractmethod
    async def sell(self, contract_id: str, price: float = 0.0) -> dict: ...

    @abc.abstractmethod
    async def update_contract(self, contract_id: str, take_profit: float | None) -> dict:
        """contract_update — post-buy take-profit management."""

    @abc.abstractmethod
    async def poll_contract(self, contract_id: str) -> OpenContract:
        """proposal_open_contract snapshot."""
