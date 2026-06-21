"""Tests for the baseline manager and Welford running statistics."""

from __future__ import annotations

import statistics

from procai.core.baseline import BaselineManager, RunningStat
from procai.core.models import ProcessSnapshot


def test_running_stat_matches_statistics():
    rs = RunningStat()
    xs = [10, 12, 11, 9, 10, 13, 8, 12, 11, 10, 14, 7]
    for x in xs:
        rs.update(x)
    assert rs.count == len(xs)
    assert abs(rs.mean - statistics.mean(xs)) < 1e-9
    assert abs(rs.std - statistics.stdev(xs)) < 1e-9
    assert rs.min_value == min(xs)
    assert rs.max_value == max(xs)


def test_zscore_is_bounded_and_zero_when_immature():
    rs = RunningStat()
    assert rs.zscore(100) == 0.0  # count < 2
    rs.update(10)
    rs.update(10)
    # Constant metric: a big jump should be clamped, not infinite.
    assert abs(rs.zscore(10_000)) <= 12.0


def _snap(cpu, mem=5.0, threads=20, conns=2):
    return ProcessSnapshot(pid=1, name="app.exe", exe_path="C:/app.exe",
                           cpu_percent=cpu, memory_percent=mem,
                           memory_rss=100 * 1024 * 1024, num_threads=threads,
                           num_connections=conns)


def test_baseline_unavailable_until_min_samples(db):
    bm = BaselineManager(db, min_samples=8)
    for _ in range(3):
        bm.update(_snap(10))
    assert bm.deviation(_snap(10)).available is False


def test_baseline_detects_anomaly(db):
    bm = BaselineManager(db, min_samples=5)
    for i in range(10):
        bm.update(_snap(10 + (i % 3)))  # ~10-12% cpu
    normal = bm.deviation(_snap(11))
    assert normal.available and normal.max_abs_z < 3.0
    anomalous = bm.deviation(_snap(99, mem=80, threads=900, conns=150))
    assert anomalous.max_abs_z >= 3.0
    assert anomalous.deviating_metrics


def test_baseline_persists_across_managers(db):
    bm1 = BaselineManager(db, min_samples=5)
    for _ in range(6):
        bm1.update(_snap(10))
    bm2 = BaselineManager(db, min_samples=5)  # fresh cache, same DB
    assert bm2.identity_maturity("c:/app.exe") >= 6
