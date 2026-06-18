"""Tests for numeric helpers, the YAML-lite loader and config resolution."""

import unittest

from accuscan import mathx
from accuscan.config import load_config
from accuscan.yaml_lite import load_yaml


class TestMathx(unittest.TestCase):
    def test_basic_stats(self):
        xs = [1, 2, 3, 4]
        self.assertAlmostEqual(mathx.mean(xs), 2.5)
        self.assertAlmostEqual(mathx.median(xs), 2.5)
        self.assertAlmostEqual(mathx.median([1, 2, 3]), 2.0)
        self.assertGreater(mathx.std(xs), 0)

    def test_clamp_safe_div(self):
        self.assertEqual(mathx.clamp(1.5), 1.0)
        self.assertEqual(mathx.clamp(-0.5), 0.0)
        self.assertEqual(mathx.safe_div(1, 0, default=9), 9)

    def test_linreg_slope(self):
        # y = 2x has slope 2
        self.assertAlmostEqual(mathx.linreg_slope([0, 2, 4, 6]), 2.0, places=6)

    def test_percentile(self):
        xs = list(range(0, 101))
        self.assertAlmostEqual(mathx.percentile(xs, 50), 50.0, places=6)
        self.assertAlmostEqual(mathx.percentile(xs, 99), 99.0, places=6)

    def test_entropy_uniform_max(self):
        probs = [0.1] * 10
        self.assertAlmostEqual(mathx.shannon_entropy_bits(probs), 3.321928, places=4)


class TestYamlLite(unittest.TestCase):
    def test_nested_and_flow_list(self):
        text = (
            "scanner:\n"
            "  windows: [25, 50, 100]\n"
            "  primary_window: 100\n"
            "  names: [\"R_10\", \"1HZ\"]\n"
            "digits:\n"
            "  danger_digits: [0, 1, 5]  # comment\n"
            "  enabled: true\n"
        )
        d = load_yaml(text)
        self.assertEqual(d["scanner"]["windows"], [25, 50, 100])
        self.assertEqual(d["scanner"]["primary_window"], 100)
        self.assertEqual(d["scanner"]["names"], ["R_10", "1HZ"])
        self.assertEqual(d["digits"]["danger_digits"], [0, 1, 5])
        self.assertIs(d["digits"]["enabled"], True)

    def test_scientific_float(self):
        d = load_yaml("movement:\n  zero_move_eps: 1.0e-9\n")
        self.assertAlmostEqual(d["movement"]["zero_move_eps"], 1e-9)


class TestConfig(unittest.TestCase):
    def test_default_weights_sum_to_one(self):
        cfg = load_config()
        w = cfg.section("scoring")["weights"]
        self.assertAlmostEqual(sum(w.values()), 1.0, places=6)

    def test_profiles_load(self):
        for prof in ("conservative", "moderate", "aggressive"):
            cfg = load_config(risk_profile=prof)
            self.assertEqual(cfg.risk_profile.name, prof)
            self.assertGreater(cfg.risk_profile.ready_threshold, 0)
            self.assertIn("max_daily_loss", cfg.risk_profile.safeguards)

    def test_danger_digits_default(self):
        cfg = load_config()
        self.assertEqual(cfg.section("digits")["danger_digits"], [0, 1, 5])


if __name__ == "__main__":
    unittest.main()
