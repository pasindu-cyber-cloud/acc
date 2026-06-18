"""Test package bootstrap.

Inserts the `src/` layout onto sys.path so the suite runs both under
`python -m unittest discover -s tests` (no install needed) and under pytest.
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
