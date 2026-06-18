"""AccuScan application orchestrator.

Boots the configured data source, discovers ACCU-eligible symbols, seeds
history, subscribes to ticks and drives the MarketScanner. A shared snapshot is
republished on an interval for the console and/or HTTP dashboard.

Offline-friendly: with ACCUSCAN_DATA_SOURCE=mock everything runs with no
network. `--ticks N` bounds a run for demos/CI.

    python -m accuscan.app --mode paper --profile moderate --ticks 600
    python -m accuscan.app --dashboard            # serve HTTP dashboard
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import time

from .audit import AuditLogger
from .config import AppConfig, load_config, validate_execution_allowed
from .constants import DataSource, Mode
from .scanner import MarketScanner, SymbolRegistry
from .storage import Storage
from .transport.base import MarketDataSource


def build_source(cfg: AppConfig) -> MarketDataSource:
    if cfg.data_source is DataSource.MOCK:
        from .transport.mock_source import MockDataSource
        return MockDataSource(symbols=cfg.symbols or None, tick_interval=0.05)
    if cfg.data_source is DataSource.DERIV:
        from .transport.deriv_ws import DerivWSClient
        return DerivWSClient(
            app_id=cfg.deriv.app_id, ws_url=cfg.deriv.ws_url,
            api_token=cfg.deriv.api_token, currency=cfg.deriv.currency,
        )
    raise ValueError(f"Unsupported data source for live run: {cfg.data_source}")


class Application:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        ok, msg = validate_execution_allowed(cfg)
        if not ok:
            # Never silently downgrade; refuse to start in an unsafe combo.
            raise SystemExit(f"Execution not allowed: {msg}")
        self.storage = Storage(cfg.db_url) if cfg.section("logging").get("persist_scores", True) else None
        self.audit = AuditLogger(storage=self.storage, mode=cfg.mode.value)
        self.scanner = MarketScanner(cfg, audit=self.audit)
        self.registry = SymbolRegistry()
        self.source: MarketDataSource | None = None
        self._snapshot: dict = {}
        self._stop = asyncio.Event()

    def snapshot(self) -> dict:
        return self._snapshot

    async def setup(self) -> list[str]:
        self.source = build_source(self.cfg)
        await self.source.connect()
        scn = self.cfg.section("scanner")
        symbols_info = await self.registry.discover(
            self.source, self.cfg.risk_profile,
            max_symbols=scn.get("max_symbols", 24),
            require_accu=scn.get("require_accu_contract", True),
            preferred_families=scn.get("preferred_families"),
            explicit_symbols=self.cfg.symbols or None,
        )
        symbols = [s.symbol for s in symbols_info]
        seed_count = scn.get("seed_history_count", 1000)
        for info in symbols_info:
            self.scanner.register_symbol(info.symbol, family=info.family)
            try:
                hist = await self.source.history(info.symbol, seed_count)
                self.scanner.seed(info.symbol, hist)
            except Exception as exc:  # pragma: no cover - network dependent
                self.audit.log_rejection(info.symbol, 0, [f"seed_failed:{exc}"])
        return symbols

    async def run(self, symbols: list[str], max_ticks: int | None = None,
                  rank_interval: float = 0.5) -> None:
        assert self.source is not None
        stream = await self.source.subscribe(symbols)
        last_rank = 0.0
        last_ping = 0.0
        count = 0
        async for tick in stream:
            self.scanner.process_tick(tick)
            count += 1
            now = time.monotonic()
            if now - last_ping > 5.0:
                with contextlib.suppress(Exception):
                    lat = await self.source.ping()
                    for s in symbols:
                        self.scanner.set_latency(s, lat)
                last_ping = now
            if now - last_rank >= rank_interval:
                self._snapshot = self.scanner.snapshot()
                last_rank = now
            if max_ticks and count >= max_ticks:
                break
            if self._stop.is_set():
                break
        self._snapshot = self.scanner.snapshot()

    async def shutdown(self) -> None:
        self._stop.set()
        if self.source is not None:
            with contextlib.suppress(Exception):
                await self.source.close()
        self.audit.close()
        if self.storage is not None:
            self.storage.close()


async def _amain(args: argparse.Namespace) -> int:
    cfg = load_config(
        mode=args.mode, risk_profile=args.profile, data_source=args.data_source,
        symbols=[s.strip() for s in args.symbols.split(",")] if args.symbols else None,
    )
    app = Application(cfg)
    symbols = await app.setup()
    print(f"AccuScan [{cfg.mode.value}/{cfg.risk_profile.name}] "
          f"source={cfg.data_source.value} symbols={symbols}")

    if args.dashboard:
        from .dashboard.server import serve
        # Run scanner loop and HTTP dashboard concurrently.
        loop_task = asyncio.create_task(app.run(symbols, max_ticks=args.ticks))
        loop_task.add_done_callback(lambda _: app._stop.set())
        try:
            await serve(app, host=cfg.dashboard_host, port=cfg.dashboard_port, stop=app._stop)
        finally:
            app._stop.set()
            await loop_task
            await app.shutdown()
        return 0

    try:
        if args.console:
            from .console.dashboard import run_console
            loop_task = asyncio.create_task(app.run(symbols, max_ticks=args.ticks))
            await run_console(app, refresh=args.refresh, stop=app._stop)
            await loop_task
        else:
            await app.run(symbols, max_ticks=args.ticks)
            _print_snapshot(app.snapshot())
    finally:
        await app.shutdown()
    return 0


def _print_snapshot(snap: dict) -> None:
    import json
    print(json.dumps({
        "mode": snap.get("mode"),
        "best_market": snap.get("best_market"),
        "second_best": snap.get("second_best"),
        "avoid_list": snap.get("avoid_list"),
        "ranking": snap.get("ranking", [])[:5],
        "paper": snap.get("paper"),
        "alerts": snap.get("alerts", [])[-5:],
    }, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AccuScan orchestrator")
    parser.add_argument("--mode", default=None, choices=["analytics", "paper", "demo", "live"])
    parser.add_argument("--profile", default=None,
                        choices=["conservative", "moderate", "aggressive"])
    parser.add_argument("--data-source", dest="data_source", default=None,
                        choices=["mock", "deriv"])
    parser.add_argument("--symbols", default=None, help="comma-separated override")
    parser.add_argument("--ticks", type=int, default=None, help="stop after N ticks")
    parser.add_argument("--dashboard", action="store_true", help="serve HTTP dashboard")
    parser.add_argument("--console", action="store_true", help="live console dashboard")
    parser.add_argument("--refresh", type=float, default=1.0)
    args = parser.parse_args(argv)
    try:
        return asyncio.run(_amain(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
