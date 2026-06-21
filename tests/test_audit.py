"""Tests for the tamper-evident audit log."""

from __future__ import annotations

import dataclasses

from procai.utils import audit


def _fresh_log(tmp_path, monkeypatch):
    log_path = tmp_path / "audit.log"
    # PATHS is a frozen dataclass; swap the whole object on the audit module.
    new_paths = dataclasses.replace(audit.PATHS, audit_path=log_path)
    monkeypatch.setattr(audit, "PATHS", new_paths)
    return log_path


def test_records_and_verifies(tmp_path, monkeypatch):
    log_path = _fresh_log(tmp_path, monkeypatch)
    audit.record("test.one", {"x": 1})
    audit.record("test.two", {"y": 2})
    entries = audit.read_all(log_path)
    assert len(entries) == 2
    assert entries[0]["action"] == "test.one"
    ok, idx = audit.verify(log_path)
    assert ok is True and idx == -1


def test_chain_links_entries(tmp_path, monkeypatch):
    log_path = _fresh_log(tmp_path, monkeypatch)
    audit.record("a")
    audit.record("b")
    entries = audit.read_all(log_path)
    assert entries[1]["prev"] == entries[0]["hash"]


def test_tamper_is_detected(tmp_path, monkeypatch):
    log_path = _fresh_log(tmp_path, monkeypatch)
    audit.record("a", {"v": 1})
    audit.record("b", {"v": 2})
    # Tamper with the first line's detail.
    lines = log_path.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace('"v":1', '"v":999')
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, idx = audit.verify(log_path)
    assert ok is False
    assert idx == 0
