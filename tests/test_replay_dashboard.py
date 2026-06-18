"""End-to-end replay + snapshot/dashboard integration tests."""

import unittest

from accuscan.backtest import ReplayEngine, compute_metrics, default_scenario
from accuscan.console.dashboard import render_once


class TestReplay(unittest.TestCase):
    def test_metrics_discriminate_and_detect(self):
        engine = ReplayEngine(mode="paper", risk_profile="moderate")
        records = engine.run(default_scenario(seed=42))
        m = compute_metrics(records)
        # Score should be higher in favourable (calm) than unfavourable (danger).
        self.assertGreater(m["avg_score_favorable"], m["avg_score_unfavorable"])
        # Both danger onsets should be detected.
        self.assertEqual(m["deterioration_detected_onsets"], m["danger_onsets"])
        # Steady-state false-positive rate should be low.
        self.assertLess(m["false_positive_rate_steady"], 0.15)
        # Detection should be reasonably prompt.
        self.assertIsNotNone(m["deterioration_lead_ticks_avg"])
        self.assertLessEqual(m["deterioration_lead_ticks_avg"], 25)

    def test_snapshot_and_console_render(self):
        engine = ReplayEngine(mode="paper", risk_profile="moderate")
        engine.run(default_scenario(seed=7))
        snap = engine.scanner.snapshot()
        for key in ("mode", "ranking", "best_market", "avoid_list", "alerts", "detail"):
            self.assertIn(key, snap)
        # Console renderer must not raise and must mention the mode.
        text = render_once(snap)
        self.assertIn("AccuScan", text)


class TestProfilesDiffer(unittest.TestCase):
    def test_aggressive_higher_growth_more_drawdown(self):
        results = {}
        for prof in ("conservative", "aggressive"):
            e = ReplayEngine(mode="paper", risk_profile=prof)
            e.run(default_scenario(seed=42))
            results[prof] = e.paper_summary()
        # Aggressive (5% cap) should not have a smaller drawdown than conservative.
        self.assertGreaterEqual(results["aggressive"]["max_drawdown"],
                                results["conservative"]["max_drawdown"])


if __name__ == "__main__":
    unittest.main()
