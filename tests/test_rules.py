"""Tests for the transparent rule engine."""

from __future__ import annotations

import time

from procai.core.models import BaselineDeviation, ProcessSnapshot, Severity
from procai.core.rules import RuleEngine


def _engine():
    return RuleEngine()


def test_benign_process_scores_zero():
    snap = ProcessSnapshot(pid=1, name="explorer.exe",
                           exe_path=r"C:\Windows\explorer.exe", cpu_percent=1.0,
                           memory_percent=1.0, num_threads=30, num_connections=2,
                           is_signed=True)
    ev = _engine().evaluate(snap)
    assert ev.score == 0.0
    assert ev.hits == []


def test_high_cpu_fires():
    snap = ProcessSnapshot(pid=1, name="x.exe", cpu_percent=95.0)
    ev = _engine().evaluate(snap)
    ids = {h.rule_id for h in ev.hits}
    assert "cpu_high" in ids
    assert ev.score > 0


def test_unsigned_in_temp_stacks():
    snap = ProcessSnapshot(pid=1, name="x.exe",
                           exe_path=r"C:\Users\u\AppData\Local\Temp\x.exe",
                           is_signed=False, in_suspicious_dir=True)
    ev = _engine().evaluate(snap)
    ids = {h.rule_id for h in ev.hits}
    assert "path_suspicious" in ids and "unsigned" in ids
    # Two corroborating indicators should outscore a single one.
    assert ev.score > 40


def test_office_spawns_shell_is_high():
    snap = ProcessSnapshot(pid=1, name="cmd.exe", parent_name="winword.exe")
    ev = _engine().evaluate(snap)
    hit = next(h for h in ev.hits if h.rule_id == "lineage_office_shell")
    assert hit.severity == Severity.HIGH


def test_score_is_bounded():
    snap = ProcessSnapshot(pid=1, name="cmd.exe", parent_name="winword.exe",
                           cpu_percent=99, memory_percent=90,
                           memory_rss=4096 * 1024 * 1024, num_threads=1000,
                           num_connections=200, num_remote_endpoints=150,
                           is_signed=False, in_suspicious_dir=True,
                           is_startup_persistent=True)
    ev = _engine().evaluate(snap)
    assert 0 <= ev.score <= 100


def test_baseline_deviation_rule():
    snap = ProcessSnapshot(pid=1, name="x.exe", create_time=time.time() - 100)
    dev = BaselineDeviation(available=True, samples=20, max_abs_z=8.0,
                            deviating_metrics=["cpu_percent", "num_threads"],
                            z_scores={"cpu_percent": 8.0, "num_threads": 5.0})
    ev = _engine().evaluate(snap, dev)
    assert any(h.rule_id == "baseline_deviation" for h in ev.hits)
