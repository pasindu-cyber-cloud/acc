"""Tests for the SQLite persistence layer."""

from __future__ import annotations

import time

from procai.core.models import Alert, ProcessSnapshot, Severity


def test_settings_roundtrip(db):
    db.set_setting("k", {"a": 1, "b": [1, 2, 3]})
    assert db.get_setting("k") == {"a": 1, "b": [1, 2, 3]}
    assert db.get_setting("missing", "default") == "default"


def test_alert_insert_and_query(db):
    a = Alert(pid=10, process_name="x.exe", risk_score=80, severity=Severity.HIGH,
              confidence=0.9, reasons=["r1", "r2"], rule_hits=["cpu_high"])
    aid = db.insert_alert(a)
    assert aid > 0
    rows = db.get_alerts()
    assert len(rows) == 1
    assert rows[0].process_name == "x.exe"
    assert rows[0].reasons == ["r1", "r2"]
    assert rows[0].severity == Severity.HIGH


def test_alert_severity_filter_and_counts(db):
    db.insert_alert(Alert(pid=1, process_name="a", risk_score=20, severity=Severity.LOW,
                          confidence=0.1))
    db.insert_alert(Alert(pid=2, process_name="b", risk_score=90, severity=Severity.CRITICAL,
                          confidence=0.9))
    high = db.get_alerts(min_severity=Severity.HIGH)
    assert len(high) == 1 and high[0].severity == Severity.CRITICAL
    counts = db.alert_counts_by_severity()
    assert counts[int(Severity.CRITICAL)] == 1


def test_acknowledge(db):
    aid = db.insert_alert(Alert(pid=1, process_name="a", risk_score=50,
                                severity=Severity.MEDIUM, confidence=0.5))
    db.acknowledge_alert(aid, "dismissed")
    assert db.get_alerts(unacknowledged_only=True) == []


def test_reputation_lists(db):
    db.add_reputation("allow", "Trusted.EXE")
    db.add_reputation("block", "bad.exe")
    assert "trusted.exe" in db.get_reputation("allow")  # stored lowercased
    db.remove_reputation("allow", "trusted.exe")
    assert db.get_reputation("allow") == []


def test_process_history_batch_and_prune(db):
    now = time.time()
    snaps = [(ProcessSnapshot(pid=i, name=f"p{i}", exe_path=f"c:/p{i}.exe",
                              timestamp=now - 40 * 86400), 10.0, 1) for i in range(5)]
    db.insert_process_snapshots(snaps)
    assert len(db.recent_process_history()) == 5
    deleted = db.prune_retention(process_history_days=14)
    assert deleted["process_history"] == 5
    assert db.recent_process_history() == []


def test_labelled_samples(db):
    db.add_labelled_sample({"cpu_percent": 90}, 1)
    db.add_labelled_sample({"cpu_percent": 5}, 0)
    assert db.labelled_sample_count() == 2
    samples = db.get_labelled_samples()
    assert {lbl for _f, lbl in samples} == {0, 1}
