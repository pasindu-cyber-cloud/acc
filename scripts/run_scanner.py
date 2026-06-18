#!/usr/bin/env python
"""Convenience launcher for the scanner/orchestrator.

Adds src/ to the path so it runs without installation:
    python scripts/run_scanner.py --mode paper --dashboard
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from accuscan.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
