"""Symbol registry.

Discovers tradable symbols dynamically (active_symbols) and keeps only those
whose contracts_for includes ACCU, then applies risk-profile family rules and a
hard cap. Never hardcodes a static watchlist (an explicit override list is
still honoured if provided).
"""

from __future__ import annotations

from ..config import RiskProfile
from ..models import SymbolInfo
from ..risk.risk_profiles import family_allowed
from ..transport.base import MarketDataSource


class SymbolRegistry:
    def __init__(self) -> None:
        self.symbols: dict[str, SymbolInfo] = {}

    async def discover(
        self,
        source: MarketDataSource,
        profile: RiskProfile,
        *,
        max_symbols: int = 24,
        require_accu: bool = True,
        preferred_families: list[str] | None = None,
        explicit_symbols: list[str] | None = None,
    ) -> list[SymbolInfo]:
        all_symbols = await source.list_symbols()
        preferred_families = preferred_families or []

        selected: list[SymbolInfo] = []
        for info in all_symbols:
            if explicit_symbols:
                if info.symbol not in explicit_symbols:
                    continue
            if require_accu and not info.accu_available:
                continue
            if preferred_families and not any(
                info.symbol.startswith(p) for p in preferred_families
            ):
                # Outside the recognised synthetic families.
                if not explicit_symbols:
                    continue
            if not family_allowed(profile, info.family) and not explicit_symbols:
                continue
            selected.append(info)

        # Stable ordering, then cap.
        selected.sort(key=lambda s: s.symbol)
        selected = selected[:max_symbols]
        self.symbols = {s.symbol: s for s in selected}
        return selected

    def family_of(self, symbol: str) -> str:
        info = self.symbols.get(symbol)
        return info.family if info else ""

    def pip_size(self, symbol: str) -> int:
        info = self.symbols.get(symbol)
        return info.pip_size if info else 2
