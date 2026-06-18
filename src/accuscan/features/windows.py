"""Rolling tick buffers (stdlib only).

A single deque of the largest window size is maintained per symbol; the
smaller windows are simple tail-slices of the same buffer. This keeps memory
O(max_window) per symbol and makes the 25/50/100/300/1000 views consistent.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from ..models import Tick


class SymbolBuffer:
    """Holds recent ticks for one symbol and exposes per-window views (lists)."""

    def __init__(self, symbol: str, windows: Iterable[int]) -> None:
        self.symbol = symbol
        self.windows = sorted(set(windows))
        self.max_window = max(self.windows)
        self._ticks: deque[Tick] = deque(maxlen=self.max_window)
        self.last_recv_ts: float = 0.0
        self.last_epoch: int = 0
        self._prev_epoch: int = 0
        self.gap_count: int = 0

    def add(self, tick: Tick) -> None:
        if self._prev_epoch and tick.epoch - self._prev_epoch > 2:
            self.gap_count += 1
        self._prev_epoch = tick.epoch
        self.last_epoch = tick.epoch
        self.last_recv_ts = tick.recv_ts
        self._ticks.append(tick)

    def seed(self, ticks: Iterable[Tick]) -> None:
        for t in ticks:
            self.add(t)

    def __len__(self) -> int:
        return len(self._ticks)

    @property
    def pip_size(self) -> int:
        return self._ticks[-1].pip_size if self._ticks else 2

    def pip_value(self) -> float:
        return 10.0 ** (-self.pip_size)

    def _tail(self, window: int) -> list[Tick]:
        if not self._ticks:
            return []
        n = len(self._ticks)
        if window >= n:
            return list(self._ticks)
        # deque slicing isn't supported directly; materialise the tail.
        return list(self._ticks)[n - window:]

    def quotes(self, window: int) -> list[float]:
        return [t.quote for t in self._tail(window)]

    def quotes_in_pips(self, window: int) -> list[float]:
        pv = self.pip_value()
        return [t.quote / pv for t in self._tail(window)]

    def digits(self, window: int) -> list[int]:
        return [t.last_digit for t in self._tail(window)]

    def deltas(self, window: int) -> list[float]:
        q = self.quotes(window + 1)
        if len(q) < 2:
            return []
        return [q[i] - q[i - 1] for i in range(1, len(q))]

    def deltas_in_pips(self, window: int) -> list[float]:
        pv = self.pip_value()
        return [d / pv for d in self.deltas(window)]
