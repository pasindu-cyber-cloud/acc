"""Tests for the hybrid anomaly engine fusion and decision logic."""

from __future__ import annotations

from procai.config import SensitivityProfile, Settings
from procai.core.baseline import BaselineManager
from procai.core.hybrid import HybridConfig, HybridEngine
from procai.core.models import ProcessSnapshot, Severity
from procai.core.rules import RuleEngine


def _engine(db):
    return HybridEngine(RuleEngine(), BaselineManager(db, min_samples=5), classifier=None)


def _cfg(**kw):
    return HybridConfig.from_settings(Settings(enable_ml=False, **kw))


def test_benign_does_not_alert(db):
    eng = _engine(db)
    snap = ProcessSnapshot(pid=1, name="explorer.exe", exe_path=r"C:\Windows\explorer.exe",
                           cpu_percent=1, memory_percent=1, num_threads=30, is_signed=True)
    r = eng.evaluate(snap, _cfg(sensitivity=SensitivityProfile.BALANCED))
    assert r.risk_score == 0.0
    assert r.should_alert is False
    assert r.severity == Severity.INFO


def test_blocklist_forces_critical_alert(db):
    eng = _engine(db)
    snap = ProcessSnapshot(pid=2, name="evil.exe", exe_path=r"C:\evil.exe")
    r = eng.evaluate(snap, _cfg(blocklist=["evil.exe"]))
    assert r.risk_score == 100.0
    assert r.severity == Severity.CRITICAL
    assert r.should_alert is True


def test_allowlist_suppresses_alert(db):
    eng = _engine(db)
    snap = ProcessSnapshot(pid=3, name="x.exe",
                           exe_path=r"C:\Users\u\AppData\Local\Temp\x.exe",
                           is_signed=False, in_suspicious_dir=True, cpu_percent=95)
    r = eng.evaluate(snap, _cfg(allowlist=["x.exe"], suppress_trusted=True,
                                sensitivity=SensitivityProfile.STRICT))
    assert r.suppressed is True
    assert r.should_alert is False


def test_strict_more_sensitive_than_low(db):
    snap = ProcessSnapshot(pid=4, name="x.exe",
                           exe_path=r"C:\Users\u\AppData\Local\Temp\x.exe",
                           is_signed=False, in_suspicious_dir=True)
    strict = _engine(db).evaluate(snap, _cfg(sensitivity=SensitivityProfile.STRICT))
    low = _engine(db).evaluate(snap, _cfg(sensitivity=SensitivityProfile.LOW))
    # Same score, but strict's lower threshold makes it at least as likely to alert.
    assert strict.risk_score == low.risk_score
    assert int(strict.should_alert) >= int(low.should_alert)


def test_components_recorded(db):
    eng = _engine(db)
    snap = ProcessSnapshot(pid=5, name="x.exe", cpu_percent=95)
    r = eng.evaluate(snap, _cfg())
    assert "rule_score" in r.components
    assert "w_rules" in r.components
    assert 0.0 <= r.confidence <= 1.0
