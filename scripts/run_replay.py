#!/usr/bin/env python
"""Convenience launcher for the replay / backtest engine.

    python scripts/run_replay.py --compare
    python scripts/run_replay.py --profile aggressive --seed 7
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from accuscan.backtest.replay_engine import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
