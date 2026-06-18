"""Market Scanner orchestrator.

Wires every engine together and drives the per-tick decision loop. The core
`process_tick` is SYNCHRONOUS and side-effect contained, so the exact same code
path is exercised by:
  * the live async `run()` loop (consuming a MarketDataSource stream), and
  * the offline replay/backtest engine (feeding historical ticks).

Per tick it: updates features -> recommends growth rate -> scores stability &
quality -> applies vetoes -> ranks markets -> manages READY baselines &
deterioration -> raises alerts -> (optionally) paper-trades -> audits.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..alerts import AlertEngine
from ..audit import AuditLogger
from ..config import AppConfig
from ..constants import AlertLevel, HealthLabel, Mode, Status
from ..deterioration import DeteriorationConfig, DeteriorationDetector
from ..execution import PaperTrader, SafeguardEngine, SafeguardLimits, capabilities
from ..features import DigitConfig, FeatureEngine, MovementConfig
from ..health import TradeHealthConfig, TradeHealthMeter
from ..models import MarketScore, StabilityFeatures, Tick
from ..risk import GrowthGovernor
from ..scoring import ScoringConfig, ScoringEngine, Weights
from ..stability import StabilityConfig, StabilityModel


@dataclass
class SymbolState:
    symbol: str
    family: str = ""
    score: MarketScore | None = None
    stability: StabilityFeatures | None = None
    deterioration: object | None = None
    trade_health: object | None = None
    ready_since_ts: float | None = None
    ticks_in_trade: int = 0
    last_status: Status | None = None
    growth_eval: dict = field(default_factory=dict)
    digit_dist: dict = field(default_factory=dict)
    move_buckets: dict = field(default_factory=dict)


class MarketScanner:
    def __init__(self, cfg: AppConfig, audit: AuditLogger | None = None, clock=time.time):
        self.cfg = cfg
        self.clock = clock
        scn = cfg.section("scanner")
        self.windows = scn.get("windows", [25, 50, 100, 300, 1000])
        self.primary_window = scn.get("primary_window", 100)
        self.min_count = self.primary_window
        digits_cfg = cfg.section("digits")

        self.feature_engine = FeatureEngine(
            self.windows,
            DigitConfig.from_dict(digits_cfg),
            MovementConfig.from_dict(cfg.section("movement")),
            staleness_warn_ms=cfg.section("deterioration").get("staleness_warn_ms", 3000.0),
        )
        self.stability_model = StabilityModel(
            StabilityConfig.from_dict(scn, cfg.section("stability"))
        )
        self.scoring = ScoringEngine(
            ScoringConfig.from_dict(cfg.section("scoring"), cfg.risk_profile),
            Weights.from_dict(cfg.section("scoring").get("weights")),
            cfg.risk_profile,
            danger_digit_count=len(digits_cfg.get("danger_digits", [0, 1, 5])),
            entropy_floor=digits_cfg.get("entropy_floor", 2.6),
            danger_z_short=digits_cfg.get("danger_z_short", 3.0),
            danger_z_primary=digits_cfg.get("danger_z_primary", 3.0),
        )
        self.deterioration = DeteriorationDetector(
            DeteriorationConfig.from_dict(cfg.section("deterioration"))
        )
        self.alerts = AlertEngine()
        self.trade_health = TradeHealthMeter(
            TradeHealthConfig.from_dict(cfg.section("trade_health"))
        )
        gov_cfg = cfg.section("growth_governor")
        self.governor = GrowthGovernor(
            allowed_rates=tuple(gov_cfg.get("allowed_rates", [0.01, 0.02, 0.03, 0.04, 0.05]))
        )
        self.audit = audit

        # Execution wiring (paper only here; demo/live handled in app.py).
        self.caps = capabilities(cfg.mode)
        self.safeguards = SafeguardEngine(
            SafeguardLimits.from_profile(cfg.risk_profile),
            cfg.mode,
            live_confirmed=cfg.live_confirmed,
            clock=clock,
        )
        exec_cfg = cfg.section("execution")
        self.paper = (
            PaperTrader(start_balance=exec_cfg.get("paper_start_balance", 1000.0))
            if cfg.mode is Mode.PAPER else None
        )
        self.stake = exec_cfg.get("stake_per_trade", 1.0)
        self.tp_pct = exec_cfg.get("default_take_profit_pct", 0.20)

        self.states: dict[str, SymbolState] = {}

    # --- registration -------------------------------------------------------
    def register_symbol(self, symbol: str, family: str = "") -> None:
        self.states[symbol] = SymbolState(symbol=symbol, family=family)

    def seed(self, symbol: str, ticks: list[Tick]) -> None:
        self.feature_engine.seed(symbol, ticks)

    def set_latency(self, symbol: str, latency_ms: float) -> None:
        self.feature_engine.set_latency(symbol, latency_ms)

    # --- core per-tick path -------------------------------------------------
    def process_tick(self, tick: Tick, now: float | None = None) -> MarketScore | None:
        now = now if now is not None else self.clock()
        st = self.states.setdefault(tick.symbol, SymbolState(symbol=tick.symbol))
        self.feature_engine.ingest(tick)

        # Paper position management runs every tick (before re-entry checks).
        if self.paper is not None and self.paper.has_position(tick.symbol):
            st.ticks_in_trade += 1
            delta_pips = self._last_delta_pips(tick.symbol)
            rec = self.paper.on_tick(tick.symbol, delta_pips, tick.epoch)
            if rec is not None:
                self.safeguards.register_close(rec.pnl)
                st.ticks_in_trade = 0
                if self.audit:
                    self.audit.log_trade(rec)

        if not self.feature_engine.ready(tick.symbol, self.min_count):
            return None

        bundle = self.feature_engine.compute(tick.symbol, now_monotonic=now)

        # Adaptive growth rate from current conditions.
        rec = self.governor.recommend(
            bundle, self.stability_model, self.cfg.risk_profile,
            deterioration_score=getattr(st.deterioration, "deterioration_score", 0.0),
        )
        st.growth_eval = rec.evaluated

        stability = self.stability_model.compute(bundle, growth_rate=rec.growth_rate)
        score = self.scoring.score(bundle, stability, family=st.family)
        score.suggested_growth_rate = rec.growth_rate

        st.score = score
        st.stability = stability

        # Capture compact chart data for the dashboard (primary window).
        d100 = bundle.digit[self.primary_window]
        m100 = bundle.movement[self.primary_window]
        st.digit_dist = {str(k): round(v, 4) for k, v in d100.distribution.items()}
        st.move_buckets = {
            "zero": m100.zero_move_count,
            "small": m100.unit_move_count,
            "large": m100.large_move_count,
        }

        # Audit on status change.
        if self.audit and st.last_status != score.status:
            self.audit.log_score(score)
        st.last_status = score.status

        # Score-veto alerts.
        for alert in self.alerts.from_score(score, now=now):
            if self.audit:
                self.audit.log_alert(alert)

        # --- readiness baseline & deterioration ----------------------------
        actionable = self.scoring.is_actionable(score)
        if actionable and st.ready_since_ts is None:
            st.ready_since_ts = now
        elif not actionable and not self.paper_has_position(tick.symbol):
            st.ready_since_ts = None

        # Maintain a deterioration baseline once a market is actionable (or in
        # a trade); update it every tick thereafter.
        monitoring = actionable or self.paper_has_position(tick.symbol)
        if monitoring and not self.deterioration.has_baseline(tick.symbol):
            self.deterioration.set_baseline(score, stability, bundle)
        if self.deterioration.has_baseline(tick.symbol):
            det = self.deterioration.update(score, stability, bundle)
            st.deterioration = det
            if self.audit:
                self.audit.log_deterioration(det)
            for alert in self.alerts.from_deterioration(det, now=now):
                if self.audit:
                    self.audit.log_alert(alert)
            # Trade-health meter if we have a baseline.
            base = self.deterioration.baseline(tick.symbol)
            if base is not None:
                st.trade_health = self.trade_health.evaluate(
                    base, score, stability, bundle, ticks_in_trade=st.ticks_in_trade
                )
        else:
            st.deterioration = None
            st.trade_health = None

        # --- paper trading --------------------------------------------------
        if self.paper is not None:
            self._maybe_paper_trade(tick, score, st, now)

        return score

    def paper_has_position(self, symbol: str) -> bool:
        return self.paper is not None and self.paper.has_position(symbol)

    def _maybe_paper_trade(self, tick: Tick, score: MarketScore, st: SymbolState, now: float) -> None:
        assert self.paper is not None
        if self.paper.has_position(tick.symbol):
            # Exit on critical deterioration / EXIT health label.
            det = st.deterioration
            health = st.trade_health
            should_exit = (
                (det is not None and det.alert_level is AlertLevel.CRITICAL)
                or (health is not None and health.label in
                    (HealthLabel.EXIT_IF_POSSIBLE, HealthLabel.CRITICAL))
            )
            if should_exit:
                rec = self.paper.exit(tick.symbol, tick.epoch, reason="deterioration_exit")
                if rec is not None:
                    self.safeguards.register_close(rec.pnl)
                    st.ticks_in_trade = 0
                    if self.audit:
                        self.audit.log_trade(rec, event="trade_exit")
            return

        # Entry attempt.
        if not self.scoring.is_actionable(score):
            return
        dwell = (now - st.ready_since_ts) if st.ready_since_ts else 0.0
        active_critical = bool(st.deterioration and st.deterioration.alert_level is AlertLevel.CRITICAL)
        decision = self.safeguards.can_enter(
            score=score,
            deterioration=st.deterioration,
            active_critical_alert=active_critical,
            ready_dwell_sec=dwell,
            proposed_growth_rate=score.suggested_growth_rate,
        )
        if not decision:
            if self.audit:
                self.audit.log_rejection(tick.symbol, tick.epoch, decision.reasons)
            return

        recent_std = self._recent_std_pips(tick.symbol)
        take_profit = self.stake * self.tp_pct
        self.paper.enter(
            symbol=tick.symbol, stake=self.stake, growth_rate=score.suggested_growth_rate,
            recent_std_pips=recent_std, entry_epoch=tick.epoch,
            take_profit=take_profit, entry_mqs=score.mqs,
        )
        self.safeguards.register_open()
        st.ticks_in_trade = 0
        if self.audit:
            self.audit.log_proposal(tick.symbol, score.suggested_growth_rate, self.stake, take_profit)

    # --- helpers ------------------------------------------------------------
    def _last_delta_pips(self, symbol: str) -> float:
        d = self.feature_engine.buffer(symbol).deltas_in_pips(2)
        return d[-1] if d else 0.0

    def _recent_std_pips(self, symbol: str) -> float:
        buf = self.feature_engine.buffer(symbol)
        d = buf.deltas_in_pips(self.scoring.cfg.short_window)
        from .. import mathx
        return mathx.std(d) if d else 1.0

    # --- ranking & snapshot -------------------------------------------------
    def rank(self) -> list[MarketScore]:
        scored = [s.score for s in self.states.values() if s.score is not None]
        scored.sort(key=lambda x: x.mqs, reverse=True)
        return scored

    def snapshot(self) -> dict:
        ranked = self.rank()
        rows = []
        best = second = None
        avoid = []
        for score in ranked:
            st = self.states[score.symbol]
            det = st.deterioration
            health = st.trade_health
            row = {
                "symbol": score.symbol,
                "mqs": score.mqs,
                "stability": score.stability_score,
                "danger_count": score.danger_count,
                "danger_pct": round(score.danger_pct * 100, 2),
                "movement_risk": score.movement_risk_score,
                "jump_risk": score.jump_risk_score,
                "trend_smooth": score.trend_smooth_score,
                "deterioration": getattr(det, "deterioration_score", 0.0),
                "data_quality": score.data_quality_score,
                "status": score.status.value,
                "suggested_growth_rate": score.suggested_growth_rate,
                "confidence": score.confidence,
                "health": getattr(health, "label", None).value if health else "-",
                "veto": score.veto_reasons,
            }
            rows.append(row)
            if score.status is Status.READY and best is None:
                best = score.symbol
            elif score.status is Status.READY and second is None:
                second = score.symbol
            if score.status is Status.HIGH_RISK:
                avoid.append(score.symbol)

        snap = {
            "ts": self.clock(),
            "mode": self.cfg.mode.value,
            "risk_profile": self.cfg.risk_profile.name,
            "ranking": rows,
            "best_market": best,
            "second_best": second,
            "avoid_list": avoid,
            "alerts": [
                {"symbol": a.symbol, "level": a.level.value, "reason": a.reason.value,
                 "message": a.message, "epoch": a.epoch}
                for a in self.alerts.recent(25)
            ],
        }
        if self.paper is not None:
            snap["paper"] = self.paper.summary()

        # Compact per-symbol detail for charts (best & second only, to bound
        # payload size): digit histogram, movement-size buckets, growth eval,
        # trade-health components.
        detail: dict = {}
        for sym in (best, second):
            if not sym:
                continue
            s = self.states.get(sym)
            if not s:
                continue
            th = getattr(s.trade_health, "components", {}) if s.trade_health else {}
            detail[sym] = {
                "digit_distribution": s.digit_dist,
                "move_buckets": s.move_buckets,
                "growth_eval": s.growth_eval,
                "trade_health_components": th,
                "deterioration": getattr(s.deterioration, "deterioration_score", 0.0),
                "deterioration_reasons": getattr(s.deterioration, "reasons", []),
            }
        snap["detail"] = detail
        return snap
