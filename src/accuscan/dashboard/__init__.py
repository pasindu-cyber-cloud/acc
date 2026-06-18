"""Dashboard package.

`server.serve` is the zero-dependency stdlib HTTP dashboard (default).
`fastapi_server.create_app` is the optional FastAPI + WebSocket variant.
"""

from .server import serve

__all__ = ["serve"]
