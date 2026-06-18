"""Tests for detectors, deterioration, safeguards, paper trader and governor."""

import unittest

from accuscan.config import load_config
from accuscan.constants import Mode, Status
from accuscan.deterioration import CUSUM, DeteriorationConfig, DeteriorationDetector
from accuscan.execution import PaperTrader, SafeguardEngine, SafeguardLimits
from accuscan.features import DigitConfig, FeatureEngine, MovementConfig
from accuscan.models import MarketScore, SubScores, Tick
from accuscan.risk import GrowthGovernor
from accuscan.scoring import ScoringConfig, ScoringEngine, Weights
from accuscan.stability import StabilityConfig, StabilityModel
from accuscan.transport.mock_source import deterministic_series

WINDOWS = [25, 50, 100, 300, 1000]


class TestCUSUM(unittest.TestCase):
    def test_triggers_then_recovers_due_to_cap(self):
        c = CUSUM(k=0.5, h=5.0, cap_mult=2.0)
        for _ in range(50):
            c.update(3.0)  # strong positive shift
        self.assertTrue(c.triggered)
        self.assertLessEqual(c.value, c.cap)  # capped
        ticks = 0
        while c.triggered and ticks < 100:
            c.update(0.0)  # signal back to baseline
            ticks += 1
        self.assertFalse(c.triggered)
        self.assertLess(ticks, 30)  # recovers quickly thanks to the cap


class TestDeterioration(unittest.TestCase):
    def _scanner_bits(self):
        cfg = load_config()
        fe = FeatureEngine(WINDOWS, DigitConfig.from_dict(cfg.section("digits")),
                           MovementConfig.from_dict(cfg.section("movement")))
        sm = StabilityModel(StabilityConfig.from_dict(cfg.section("scanner"),
                                                      cfg.section("stability")))
        sc = ScoringEngine(ScoringConfig.from_dict(cfg.section("scoring"), cfg.risk_profile),
                           Weights.from_dict(cfg.section("scoring")["weights"]),
                           cfg.risk_profile)
        dd = DeteriorationDetector(DeteriorationConfig.from_dict(cfg.section("deterioration")))
        return fe, sm, sc, dd

    def test_detects_regime_shift(self):
        fe, sm, sc, dd = self._scanner_bits()
        calm = deterministic_series(400, regime="CALM", sigma=0.05, seed=2)
        ep = 0
        for p in calm:
            ep += 1
            fe.ingest(Tick(symbol="S", epoch=ep, quote=p, pip_size=4, recv_ts=float(ep)))
        b = fe.compute("S", now_monotonic=float(ep))
        st = sm.compute(b, 0.03)
        score = sc.score(b, st, "R_")
        dd.set_baseline(score, st, b)

        import random
        rng = random.Random(5)
        last = calm[-1]
        worst = 0.0
        fired_critical = False
        for _ in range(120):
            inc = rng.gauss(0, 0.05)
            if rng.random() < 0.15:
                inc += rng.choice((-1, 1)) * 0.05 * 20
            last = max(last + inc, 0.0001)
            ep += 1
            fe.ingest(Tick(symbol="S", epoch=ep, quote=round(last, 4), pip_size=4, recv_ts=float(ep)))
            b = fe.compute("S", now_monotonic=float(ep))
            st = sm.compute(b, 0.03)
            score = sc.score(b, st, "R_")
            r = dd.update(score, st, b)
            worst = max(worst, r.deterioration_score)
            if r.alert_level.value == "CRITICAL":
                fired_critical = True
        self.assertTrue(fired_critical)
        self.assertGreater(worst, 50.0)


class TestSafeguards(unittest.TestCase):
    def _ready(self, **kw):
        base = dict(symbol="R_25", epoch=1, mqs=85, sub_scores=SubScores(),
                    status=Status.READY, ready_persistence=30, data_quality_score=95)
        base.update(kw)
        return MarketScore(**base)

    def test_blocks_and_allows(self):
        clock = [1000.0]
        sg = SafeguardEngine(SafeguardLimits(min_ready_persistence_ticks=15, min_ready_dwell_sec=20,
                                             max_concurrent_trades=1, max_trades_per_hour=4,
                                             max_growth_rate=0.03),
                             Mode.PAPER, clock=lambda: clock[0])
        self.assertTrue(sg.can_enter(self._ready(), None, False, 25.0, 0.02))
        self.assertFalse(sg.can_enter(self._ready(status=Status.WATCH), None, False, 25.0, 0.02))
        self.assertIn("growth_rate_above_cap",
                      sg.can_enter(self._ready(), None, False, 25.0, 0.05).reasons)
        sg.register_open()
        self.assertIn("max_concurrent_trades",
                      sg.can_enter(self._ready(), None, False, 25.0, 0.02).reasons)
        sg.register_close(-5.0)
        self.assertIn("loss_cooldown",
                      sg.can_enter(self._ready(), None, False, 25.0, 0.02).reasons)

    def test_live_requires_confirm(self):
        sg = SafeguardEngine(SafeguardLimits(), Mode.LIVE, live_confirmed=False, clock=lambda: 0.0)
        self.assertIn("live_not_confirmed",
                      sg.can_enter(self._ready(), None, False, 999, 0.01).reasons)


class TestPaperTrader(unittest.TestCase):
    def test_knockout_and_take_profit(self):
        pt = PaperTrader(start_balance=100.0)
        pt.enter("R_25", stake=1.0, growth_rate=0.03, recent_std_pips=10.0,
                 entry_epoch=0, take_profit=0.5)
        rec = None
        for i in range(300):
            rec = pt.on_tick("R_25", delta_pips=2.0, epoch=i)
            if rec:
                break
        self.assertIsNotNone(rec)
        self.assertEqual(rec.exit_reason, "take_profit")
        self.assertGreater(rec.pnl, 0)

        pt.enter("R_50", stake=1.0, growth_rate=0.03, recent_std_pips=10.0, entry_epoch=0)
        rec2 = pt.on_tick("R_50", delta_pips=10_000.0, epoch=1)
        self.assertEqual(rec2.exit_reason, "knockout")
        self.assertEqual(rec2.pnl, -1.0)


class TestGrowthGovernor(unittest.TestCase):
    def test_calm_allows_higher_than_jumpy(self):
        cfg = load_config(risk_profile="aggressive")
        sm = StabilityModel(StabilityConfig.from_dict(cfg.section("scanner"),
                                                      cfg.section("stability")))
        gov = GrowthGovernor()
        fe_calm = FeatureEngine(WINDOWS, DigitConfig.from_dict(cfg.section("digits")),
                                MovementConfig.from_dict(cfg.section("movement")))
        for i, p in enumerate(deterministic_series(800, regime="CALM", sigma=0.06, seed=3)):
            fe_calm.ingest(Tick(symbol="C", epoch=i, quote=p, pip_size=4, recv_ts=float(i)))
        calm_rate = gov.recommend(fe_calm.compute("C", now_monotonic=800.0), sm,
                                  cfg.risk_profile, 0.0).growth_rate

        fe_j = FeatureEngine(WINDOWS, DigitConfig.from_dict(cfg.section("digits")),
                             MovementConfig.from_dict(cfg.section("movement")))
        for i, p in enumerate(deterministic_series(800, regime="JUMPY", sigma=0.3, seed=3)):
            fe_j.ingest(Tick(symbol="J", epoch=i, quote=p, pip_size=2, recv_ts=float(i)))
        jumpy_rate = gov.recommend(fe_j.compute("J", now_monotonic=800.0), sm,
                                   cfg.risk_profile, 80.0).growth_rate
        self.assertGreaterEqual(calm_rate, jumpy_rate)


if __name__ == "__main__":
    unittest.main()
