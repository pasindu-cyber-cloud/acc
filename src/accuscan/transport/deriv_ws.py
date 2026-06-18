"""Deriv WebSocket client.

Implements both `MarketDataSource` (public) and `ExecutionGateway` (auth)
against the current Deriv WebSocket API.

API references (verified):
  - Endpoint: wss://ws.derivws.com/websockets/v3?app_id=APP_ID
  - active_symbols, contracts_for, ticks_history (style:"ticks"),
    ticks (subscribe), proposal, buy, sell, contract_update,
    proposal_open_contract, ping, time, authorize.
  - Accumulators: contract_type "ACCU", growth_rate in {0.01..0.05},
    optional limit_order.take_profit. No stop_loss for ACCU.

Compatibility notes:
  - New vs legacy `ticks_history`: legacy restricts `granularity`; we only use
    style="ticks" (no granularity) so both behave the same.
  - `contracts_for` field naming has varied; we defensively scan multiple
    shapes when extracting growth rates / contract categories.

NOTE: This module performs live network I/O. In an offline sandbox use the
`mock` data source instead (see mock_source.py).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

try:
    import websockets
except ImportError:  # pragma: no cover - websockets is a runtime dep
    websockets = None  # type: ignore

from ..constants import ACCU_CONTRACT_TYPE
from ..models import OpenContract, Proposal, SymbolInfo, Tick
from .base import ExecutionGateway, MarketDataSource


class DerivWSError(RuntimeError):
    pass


class DerivWSClient(MarketDataSource, ExecutionGateway):
    """Single multiplexed WS connection with req_id correlation."""

    def __init__(
        self,
        app_id: str,
        ws_url: str = "wss://ws.derivws.com/websockets/v3",
        api_token: str | None = None,
        currency: str = "USD",
    ) -> None:
        self.app_id = app_id
        self.ws_url = ws_url
        self.api_token = api_token
        self.currency = currency
        self._ws: Any = None
        self._req_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._subscriptions: dict[str, asyncio.Queue] = {}
        self._reader_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    # --- connection ---------------------------------------------------------
    @property
    def url(self) -> str:
        return f"{self.ws_url}?app_id={self.app_id}"

    async def connect(self) -> None:
        if websockets is None:
            raise DerivWSError("`websockets` package not installed.")
        self._ws = await websockets.connect(self.url, max_size=2**24, ping_interval=20)
        self._reader_task = asyncio.create_task(self._reader())

    async def close(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._reader_task
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def _reader(self) -> None:
        assert self._ws is not None
        async for raw in self._ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            await self._dispatch(msg)

    async def _dispatch(self, msg: dict[str, Any]) -> None:
        # Streamed subscription updates carry a "subscription" block.
        sub = msg.get("subscription")
        msg_type = msg.get("msg_type")
        if msg_type == "tick" and "tick" in msg:
            sub_id = (sub or {}).get("id")
            q = self._subscriptions.get(sub_id) if sub_id else None
            if q is None:
                # Fall back to symbol-keyed queue if id not yet mapped.
                symbol = msg["tick"].get("symbol")
                q = self._subscriptions.get(f"sym::{symbol}")
            if q is not None:
                await q.put(msg)
            return

        req_id = msg.get("req_id")
        if req_id is not None and req_id in self._pending:
            fut = self._pending.pop(req_id)
            if not fut.done():
                fut.set_result(msg)

    async def _call(self, payload: dict[str, Any], timeout: float = 15.0) -> dict[str, Any]:
        if self._ws is None:
            raise DerivWSError("Not connected.")
        async with self._lock:
            self._req_id += 1
            req_id = self._req_id
        payload = {**payload, "req_id": req_id}
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut
        await self._ws.send(json.dumps(payload))
        try:
            msg = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError as exc:
            self._pending.pop(req_id, None)
            raise DerivWSError(f"Timeout waiting for {payload.get('msg_type', payload)}") from exc
        if "error" in msg:
            err = msg["error"]
            raise DerivWSError(f"{err.get('code')}: {err.get('message')}")
        return msg

    # --- market data --------------------------------------------------------
    async def list_symbols(self) -> list[SymbolInfo]:
        msg = await self._call({"active_symbols": "brief", "product_type": "basic"})
        active = msg.get("active_symbols", [])
        results: list[SymbolInfo] = []
        for entry in active:
            symbol = entry.get("symbol")
            if not symbol:
                continue
            info = SymbolInfo(
                symbol=symbol,
                display_name=entry.get("display_name", symbol),
                pip_size=_pip_from_entry(entry),
                family=_family_of(symbol),
            )
            results.append(info)
        # Screen each for ACCU availability via contracts_for (concurrently).
        sem = asyncio.Semaphore(8)

        async def _screen(info: SymbolInfo) -> None:
            async with sem:
                try:
                    avail, rates = await self.accu_availability(info.symbol)
                except DerivWSError:
                    avail, rates = False, []
                info.accu_available = avail
                info.allowed_growth_rates = rates

        await asyncio.gather(*(_screen(i) for i in results))
        return results

    async def accu_availability(self, symbol: str) -> tuple[bool, list[float]]:
        msg = await self._call({"contracts_for": symbol, "currency": self.currency})
        contracts = msg.get("contracts_for", {}).get("available", [])
        rates: set[float] = set()
        found = False
        for c in contracts:
            ctype = c.get("contract_type") or c.get("contract_category")
            if ctype == ACCU_CONTRACT_TYPE or c.get("contract_category") == "accumulator":
                found = True
                # growth_rate options can appear under several keys depending
                # on API version; scan defensively.
                for key in ("growth_rate", "growth_rate_range", "multiplier_range"):
                    val = c.get(key)
                    if isinstance(val, list):
                        rates.update(float(v) for v in val if _is_number(v))
        return found, sorted(rates)

    async def history(self, symbol: str, count: int) -> list[Tick]:
        msg = await self._call(
            {
                "ticks_history": symbol,
                "count": count,
                "end": "latest",
                "style": "ticks",
            }
        )
        hist = msg.get("history", {})
        prices = hist.get("prices", [])
        times = hist.get("times", [])
        pip = await self._pip_size(symbol)
        return [
            Tick(symbol=symbol, epoch=int(t), quote=float(p), pip_size=pip, recv_ts=time.time())
            for p, t in zip(prices, times, strict=False)
        ]

    async def _pip_size(self, symbol: str) -> int:
        # active_symbols carries pip; fall back to 2 decimals.
        with suppress(Exception):
            msg = await self._call({"active_symbols": "brief"})
            for e in msg.get("active_symbols", []):
                if e.get("symbol") == symbol:
                    return _pip_from_entry(e)
        return 2

    async def subscribe(self, symbols: list[str]) -> AsyncIterator[Tick]:
        queue: asyncio.Queue = asyncio.Queue()
        pip_cache: dict[str, int] = {}
        for sym in symbols:
            # Register symbol-keyed queue first, then subscribe.
            self._subscriptions[f"sym::{sym}"] = queue
            pip_cache[sym] = await self._pip_size(sym)
            msg = await self._call({"ticks": sym, "subscribe": 1})
            sub_id = (msg.get("subscription") or {}).get("id")
            if sub_id:
                self._subscriptions[sub_id] = queue
            # An initial tick may be in the response.
            if "tick" in msg:
                await queue.put(msg)

        async def _gen() -> AsyncIterator[Tick]:
            while True:
                msg = await queue.get()
                t = msg["tick"]
                sym = t.get("symbol")
                yield Tick(
                    symbol=sym,
                    epoch=int(t.get("epoch", time.time())),
                    quote=float(t.get("quote")),
                    pip_size=pip_cache.get(sym, 2),
                    recv_ts=time.time(),
                )

        return _gen()

    async def ping(self) -> float:
        start = time.monotonic()
        await self._call({"ping": 1})
        return (time.monotonic() - start) * 1000.0

    # --- execution ----------------------------------------------------------
    async def authorize(self, token: str) -> dict:
        return await self._call({"authorize": token})

    async def propose(self, proposal: Proposal) -> Proposal:
        payload: dict[str, Any] = {
            "proposal": 1,
            "contract_type": ACCU_CONTRACT_TYPE,
            "symbol": proposal.symbol,
            "currency": proposal.currency or self.currency,
            "amount": proposal.amount,
            "basis": "stake",
            "growth_rate": proposal.growth_rate,
        }
        if proposal.take_profit is not None:
            payload["limit_order"] = {"take_profit": proposal.take_profit}
        msg = await self._call(payload)
        p = msg.get("proposal", {})
        proposal.id = p.get("id")
        proposal.spot = _safe_float(p.get("spot"))
        return proposal

    async def buy(self, proposal_id: str, price: float) -> OpenContract:
        msg = await self._call({"buy": proposal_id, "price": price})
        b = msg.get("buy", {})
        return OpenContract(
            contract_id=str(b.get("contract_id")),
            symbol=b.get("shortcode", "").split("_")[1] if b.get("shortcode") else "",
            buy_price=_safe_float(b.get("buy_price")) or price,
            growth_rate=0.0,
            entry_epoch=int(b.get("start_time", time.time())),
        )

    async def sell(self, contract_id: str, price: float = 0.0) -> dict:
        return await self._call({"sell": contract_id, "price": price})

    async def update_contract(self, contract_id: str, take_profit: float | None) -> dict:
        limit_order: dict[str, Any] = {}
        # Per docs, set to null to cancel; a number to set/update.
        limit_order["take_profit"] = take_profit
        return await self._call(
            {"contract_update": 1, "contract_id": contract_id, "limit_order": limit_order}
        )

    async def poll_contract(self, contract_id: str) -> OpenContract:
        msg = await self._call({"proposal_open_contract": 1, "contract_id": contract_id})
        c = msg.get("proposal_open_contract", {})
        return OpenContract(
            contract_id=str(c.get("contract_id", contract_id)),
            symbol=c.get("underlying", ""),
            buy_price=_safe_float(c.get("buy_price")) or 0.0,
            growth_rate=_safe_float(c.get("growth_rate")) or 0.0,
            entry_epoch=int(c.get("date_start", 0)),
            current_spot=_safe_float(c.get("current_spot")),
            profit=_safe_float(c.get("profit")) or 0.0,
            is_sold=bool(c.get("is_sold", 0)),
            status=c.get("status", "open"),
        )


# --- helpers ----------------------------------------------------------------
def _is_number(v: Any) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def _safe_float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pip_from_entry(entry: dict[str, Any]) -> int:
    pip = entry.get("pip")
    if pip:
        with suppress(Exception):
            # pip like 0.01 -> 2 decimals.
            s = f"{float(pip):.10f}".rstrip("0").rstrip(".")
            if "." in s:
                return len(s.split(".")[1])
    return int(entry.get("pip_size", 2) or 2)


def _family_of(symbol: str) -> str:
    for prefix in ("1HZ", "R_", "BOOM", "CRASH", "JD", "stpRNG"):
        if symbol.startswith(prefix):
            return prefix
    return symbol.split("_")[0] if "_" in symbol else symbol
