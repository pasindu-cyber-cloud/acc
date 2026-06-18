"""FastAPI + WebSocket dashboard (optional, production variant).

This mirrors the stdlib server but pushes snapshots over a WebSocket for lower
latency and serves the same static page. It is an OPTIONAL extra: install with
`pip install 'accuscan[dashboard]'`. If FastAPI/uvicorn are not present, import
fails loudly and the caller should fall back to `dashboard.server.serve`.

Run:
    uvicorn accuscan.dashboard.fastapi_server:create_app --factory
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse, JSONResponse
except ImportError as exc:  # pragma: no cover - optional dependency
    raise ImportError(
        "FastAPI dashboard requires the 'dashboard' extra: pip install 'accuscan[dashboard]'"
    ) from exc

_STATIC = Path(__file__).parent / "static"


def create_app(app_ref=None):
    """Build a FastAPI app. `app_ref` is an object exposing `.snapshot()`."""
    api = FastAPI(title="AccuScan Dashboard")
    state = {"app": app_ref}

    def get_snapshot() -> dict:
        a = state["app"]
        return a.snapshot() if a is not None else {}

    @api.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return (_STATIC / "index.html").read_text(encoding="utf-8")

    @api.get("/api/snapshot")
    async def snapshot() -> JSONResponse:
        return JSONResponse(get_snapshot())

    @api.get("/api/health")
    async def health() -> dict:
        return {"ok": True}

    @api.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                await websocket.send_text(json.dumps(get_snapshot(), default=str))
                await asyncio.sleep(1.0)
        except WebSocketDisconnect:
            return

    api.state.set_app = lambda a: state.__setitem__("app", a)
    return api
