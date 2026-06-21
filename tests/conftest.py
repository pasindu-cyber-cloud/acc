"""Pytest configuration: isolate ProcAI data under a temp dir and expose src/."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Ensure the src/ layout is importable without installation.
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Point ProcAI at a throwaway data dir BEFORE any procai import resolves paths.
_TMP = tempfile.mkdtemp(prefix="procai_tests_")
os.environ.setdefault("PROCAI_DATA_DIR", _TMP)

import pytest  # noqa: E402

from procai.data import Database  # noqa: E402


@pytest.fixture()
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    yield database
    database.close()
