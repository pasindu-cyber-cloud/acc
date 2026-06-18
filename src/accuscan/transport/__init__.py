"""Transport layer: isolates all I/O with Deriv (or offline substitutes).

The rest of the system depends only on the `MarketDataSource` /
`ExecutionGateway` interfaces in `base.py`, never on websocket details. This
makes it trivial to swap a live Deriv connection for the offline mock source
or the replay engine, and lets a legacy/v3-style client be dropped in behind
the same interface (compatibility wrapper).
"""

from .base import ExecutionGateway, MarketDataSource

__all__ = ["MarketDataSource", "ExecutionGateway"]
