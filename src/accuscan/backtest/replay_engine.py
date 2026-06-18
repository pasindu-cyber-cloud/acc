"""Replay / backtesting engine.

Feeds historical or synthetic ticks through the SAME MarketScanner code path
used live, records per-tick scores/status/deterioration, and computes metrics.
Supports comparing risk profiles and growth-rate policies.

CLI:
    python -m accuscan.backtest.replay_engine --profile moderate --mode paper
"""

from __future__ import annotations

import argparse
import json

from ..config import load_config
from ..scanner import MarketScanner
from ..models import Tick
from .metrics import TickRecord, compute_metrics
from .synthetic import Scenario, default_scenario


class ReplayEngine:
    def __init__(self, mode: str = "analytics", risk_profile: str = "moderate"):
        self.cfg = load_config(mode=mode, risk_profile=risk_profile, data_source="replay")
        self._clock = [0.0]
        self.scanner = MarketScanner(self.cfg, audit=None, clock=lambda: self._clock[0])

    def run(self, scenario: Scenario, seed_count: int = 100) -> list[TickRecord]:
        sym = scenario.symbol
        self.scanner.register_symbol(sym, family=_family(sym))

        # Seed initial history (so windows are warm) from the first ticks.
        seed_ticks = [
            Tick(symbol=sym, epoch=i, quote=scenario.prices[i], pip_size=scenario.pip_size, recv_ts=float(i))
            for i in range(min(seed_count, len(scenario.prices)))
        ]
        self.scanner.seed(sym, seed_ticks)

        records: list[TickRecord] = []
        for i in range(len(scenario.prices)):
            self._clock[0] = float(i)
            tick = Tick(
                symbol=sym, epoch=1_000_000 + i, quote=scenario.prices[i],
                pip_size=scenario.pip_size, recv_ts=float(i),
            )
            score = self.scanner.process_tick(tick, now=float(i))
            st = self.scanner.states[sym]
            det = st.deterioration
            records.append(TickRecord(
                epoch=tick.epoch,
                index=i,
                mqs=score.mqs if score else 0.0,
                status=score.status.value if score else "HIGH_RISK",
                deterioration=getattr(det, "deterioration_score", 0.0),
                alert_level=getattr(det, "alert_level", None).value if det else "INFO",
                danger=scenario.danger[i],
                has_baseline=self.scanner.deterioration.has_baseline(sym),
            ))
        return records

    def paper_summary(self) -> dict | None:
        return self.scanner.paper.summary() if self.scanner.paper else None


def _family(symbol: str) -> str:
    for p in ("1HZ", "R_", "BOOM", "CRASH", "JD", "stpRNG"):
        if symbol.startswith(p):
            return p
    return symbol


def compare_profiles(scenario_seed: int = 42) -> dict:
    """Run the same scenario across all three risk profiles and growth policies."""
    out: dict = {}
    for profile in ("conservative", "moderate", "aggressive"):
        engine = ReplayEngine(mode="paper", risk_profile=profile)
        scenario = default_scenario(seed=scenario_seed)
        records = engine.run(scenario)
        metrics = compute_metrics(records)
        metrics["paper"] = engine.paper_summary()
        out[profile] = metrics
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AccuScan replay / backtest")
    parser.add_argument("--profile", default="moderate",
                        choices=["conservative", "moderate", "aggressive"])
    parser.add_argument("--mode", default="paper", choices=["analytics", "paper"])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--symbol", default="R_25")
    parser.add_argument("--compare", action="store_true", help="compare all profiles")
    args = parser.parse_args(argv)

    if args.compare:
        print(json.dumps(compare_profiles(args.seed), indent=2))
        return 0

    engine = ReplayEngine(mode=args.mode, risk_profile=args.profile)
    scenario = default_scenario(symbol=args.symbol, seed=args.seed)
    records = engine.run(scenario)
    metrics = compute_metrics(records)
    metrics["paper"] = engine.paper_summary()
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
