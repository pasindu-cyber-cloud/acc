"""Tests for feature extraction (pure standard-library)."""

from __future__ import annotations

import time

from procai.core.features import FEATURE_NAMES, extract, to_vector
from procai.core.models import ProcessSnapshot


def test_feature_keys_match_names():
    snap = ProcessSnapshot(pid=1, name="x.exe")
    feats = extract(snap)
    assert set(feats) == set(FEATURE_NAMES)
    assert len(to_vector(feats)) == len(FEATURE_NAMES)


def test_unsigned_and_suspicious_flags():
    snap = ProcessSnapshot(pid=1, name="x.exe", is_signed=False, in_suspicious_dir=True)
    feats = extract(snap)
    assert feats["is_unsigned"] == 1.0
    assert feats["in_suspicious_dir"] == 1.0


def test_unknown_signature_is_not_flagged_unsigned():
    snap = ProcessSnapshot(pid=1, name="x.exe", is_signed=None)
    assert extract(snap)["is_unsigned"] == 0.0


def test_lifetime_and_memory_derived():
    now = time.time()
    snap = ProcessSnapshot(pid=1, name="x.exe", create_time=now - 600,
                           timestamp=now, memory_rss=100 * 1024 * 1024)
    feats = extract(snap)
    assert abs(feats["lifetime_minutes"] - 10.0) < 0.1
    assert abs(feats["memory_mb"] - 100.0) < 0.5
