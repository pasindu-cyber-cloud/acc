"""Tests for the feature engine, stability model and scoring/veto behaviour."""

import unittest

from accuscan.config import load_config
from accuscan.features import DigitConfig, FeatureEngine, MovementConfig
from accuscan.models import Tick
from accuscan.scoring import ScoringConfig, ScoringEngine, Weights
from accuscan.stability import StabilityConfig, StabilityModel
from accuscan.transport.mock_source import deterministic_series

WINDOWS = [25, 50, 100, 300, 1000]


def _engine_from_series(prices, pip_size=4):
    cfg = load_config()
    fe = FeatureEngine(
        WINDOWS,
        DigitConfig.from_dict(cfg.section("digits")),
        MovementConfig.from_dict(cfg.section("movement")),
    )
    for i, p in enumerate(prices):
        fe.ingest(Tick(symbol="X", epoch=i, quote=p, pip_size=pip_size, recv_ts=float(i)))
    return fe.compute("X", now_monotonic=float(len(prices)))


class TestFeatures(unittest.TestCase):
    def test_window_counts_and_digits(self):
        bundle = _engine_from_series(deterministic_series(500, regime="CALM", sigma=0.05, seed=1))
        self.assertEqual(bundle.digit[100].count, 100)
        self.assertEqual(bundle.movement[100].count, 100)
        # last digit always in 0..9
        self.assertTrue(0 <= bundle.digit[25].last_digit <= 9)

    def test_jumpy_has_higher_tail_ratio(self):
        calm = _engine_from_series(deterministic_series(500, regime="CALM", sigma=0.1, seed=2))
        jumpy = _engine_from_series(deterministic_series(500, regime="JUMPY", sigma=0.1, seed=2))
        self.assertGreater(jumpy.movement[100].jump_proxy, calm.movement[100].jump_proxy)


class TestStability(unittest.TestCase):
    def setUp(self):
        cfg = load_config()
        self.model = StabilityModel(StabilityConfig.from_dict(cfg.section("scanner"),
                                                              cfg.section("stability")))

    def test_calm_more_stable_than_jumpy(self):
        calm = self.model.compute(
            _engine_from_series(deterministic_series(800, regime="CALM", sigma=0.08, seed=5)), 0.03)
        jumpy = self.model.compute(
            _engine_from_series(deterministic_series(800, regime="JUMPY", sigma=0.08, seed=5)), 0.03)
        self.assertGreater(calm.stability_score, jumpy.stability_score)
        self.assertGreater(jumpy.jump_burst_prob, calm.jump_burst_prob)

    def test_barrier_risk_monotonic_in_growth(self):
        bundle = _engine_from_series(deterministic_series(800, regime="CALM", sigma=0.08, seed=6))
        risks = [self.model.compute(bundle, gr).barrier_risk for gr in (0.01, 0.03, 0.05)]
        self.assertLess(risks[0], risks[1])
        self.assertLess(risks[1], risks[2])


class TestScoringVeto(unittest.TestCase):
    def _score(self, prices, pip_size=4):
        cfg = load_config(risk_profile="moderate")
        bundle = _engine_from_series(prices, pip_size)
        model = StabilityModel(StabilityConfig.from_dict(cfg.section("scanner"),
                                                         cfg.section("stability")))
        stability = model.compute(bundle, 0.03)
        eng = ScoringEngine(
            ScoringConfig.from_dict(cfg.section("scoring"), cfg.risk_profile),
            Weights.from_dict(cfg.section("scoring")["weights"]),
            cfg.risk_profile, danger_digit_count=3)
        return eng.score(bundle, stability, family="R_")

    def test_uniform_digits_not_vetoed(self):
        score = self._score(deterministic_series(600, regime="CALM", sigma=0.06, seed=11))
        # A calm uniform-digit series should not trip digit vetoes.
        self.assertNotIn("danger_digit_excess_25", score.veto_reasons)
        self.assertGreater(score.sub_scores.digit_clean_100, 80.0)

    def test_jumpy_is_high_risk(self):
        score = self._score(deterministic_series(600, regime="JUMPY", sigma=0.4, seed=12), pip_size=2)
        self.assertEqual(score.status.value, "HIGH_RISK")
        self.assertTrue(len(score.veto_reasons) >= 1)


if __name__ == "__main__":
    unittest.main()
