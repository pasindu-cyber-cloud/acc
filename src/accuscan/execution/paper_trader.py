"""Paper trader.

Simulates Accumulator economics locally so the full decision pipeline can be
exercised on live or replayed ticks WITHOUT placing any order.

Accumulator payoff model (simulation proxy — NOT Deriv's exact barrier):
  - Each tick the spot stays inside a band around the previous spot, the
    position value compounds: value = stake * (1 + growth_rate) ** ticks.
  - The band half-width is approximated from recent volatility and the growth
    rate: wider for low growth, narrower for high growth (matching Deriv's
    "higher growth rate => narrower range"). A tick whose |move| exceeds the
    band is a KNOCKOUT and the stake is lost.
  - take_profit (currency) triggers an automatic cash-out (a win) once the
    accumulated profit reaches it.

The exact live barrier comes from the Deriv `proposal` (high/low barrier /
tick_size_barrier); this proxy is only for paper/replay analytics. The factor
is documented and configurable so replay results can be calibrated.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import TradeRecord
from ..stability.stability_model import growth_tightness


def band_halfwidth_pips(recent_std_pips: float, growth_rate: float, base_k: float = 3.0) -> float:
    """Approximate per-tick barrier half-width in pips.

    factor = base_k / growth_tightness(rate): ~3.0 at 1% growth (wide band),
    ~1.1 at 5% growth (narrow band). Multiplied by recent per-tick volatility.
    """
    return max(recent_std_pips, 1e-9) * (base_k / growth_tightness(growth_rate))


@dataclass
class PaperPosition:
    symbol: str
    stake: float
    growth_rate: float
    entry_epoch: int
    take_profit: float | None
    band_pips: float
    entry_mqs: float = 0.0
    ticks: int = 0
    value: float = field(init=False)

    def __post_init__(self) -> None:
        self.value = self.stake

    @property
    def profit(self) -> float:
        return self.value - self.stake


class PaperTrader:
    def __init__(self, start_balance: float = 1000.0, base_k: float = 3.0) -> None:
        self.start_balance = start_balance
        self.balance = start_balance
        self.base_k = base_k
        self.positions: dict[str, PaperPosition] = {}
        self.closed: list[TradeRecord] = []
        self.equity_curve: list[float] = [start_balance]

    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions

    def enter(
        self,
        symbol: str,
        stake: float,
        growth_rate: float,
        recent_std_pips: float,
        entry_epoch: int,
        take_profit: float | None = None,
        entry_mqs: float = 0.0,
    ) -> PaperPosition:
        band = band_halfwidth_pips(recent_std_pips, growth_rate, self.base_k)
        pos = PaperPosition(
            symbol=symbol, stake=stake, growth_rate=growth_rate, entry_epoch=entry_epoch,
            take_profit=take_profit, band_pips=band, entry_mqs=entry_mqs,
        )
        self.positions[symbol] = pos
        return pos

    def on_tick(self, symbol: str, delta_pips: float, epoch: int) -> TradeRecord | None:
        pos = self.positions.get(symbol)
        if pos is None:
            return None
        pos.ticks += 1

        # Knockout check (per-tick band breach).
        if abs(delta_pips) > pos.band_pips:
            return self._close(pos, epoch, pnl=-pos.stake, reason="knockout")

        # Compound surviving tick.
        pos.value = pos.stake * (1.0 + pos.growth_rate) ** pos.ticks
        if pos.take_profit is not None and pos.profit >= pos.take_profit:
            return self._close(pos, epoch, pnl=pos.profit, reason="take_profit")
        return None

    def exit(self, symbol: str, epoch: int, reason: str = "manual") -> TradeRecord | None:
        pos = self.positions.get(symbol)
        if pos is None:
            return None
        return self._close(pos, epoch, pnl=pos.profit, reason=reason)

    def _close(self, pos: PaperPosition, epoch: int, pnl: float, reason: str) -> TradeRecord:
        self.balance += pnl
        self.equity_curve.append(self.balance)
        rec = TradeRecord(
            symbol=pos.symbol, mode="paper", entry_epoch=pos.entry_epoch, exit_epoch=epoch,
            growth_rate=pos.growth_rate, stake=pos.stake, take_profit=pos.take_profit,
            pnl=round(pnl, 4), exit_reason=reason, entry_mqs=pos.entry_mqs, accepted=True,
        )
        self.closed.append(rec)
        del self.positions[pos.symbol]
        return rec

    # --- summary ------------------------------------------------------------
    def summary(self) -> dict:
        wins = [t for t in self.closed if t.pnl > 0]
        losses = [t for t in self.closed if t.pnl <= 0]
        peak = self.start_balance
        max_dd = 0.0
        for eq in self.equity_curve:
            peak = max(peak, eq)
            max_dd = max(max_dd, peak - eq)
        return {
            "start_balance": self.start_balance,
            "balance": round(self.balance, 2),
            "net_pnl": round(self.balance - self.start_balance, 2),
            "trades": len(self.closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(self.closed), 4) if self.closed else 0.0,
            "max_drawdown": round(max_dd, 2),
        }
