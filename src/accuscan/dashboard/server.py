"""Stdlib HTTP dashboard server (zero dependencies).

Serves a single-page dashboard plus a JSON snapshot endpoint that the page
polls. Used as the default so the dashboard runs anywhere; a FastAPI + WebSocket
variant is provided in `fastapi_server.py` for production deployments.

Endpoints:
  GET /                -> dashboard HTML
  GET /api/snapshot    -> current MarketScanner snapshot (JSON)
  GET /api/health      -> liveness probe
"""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_STATIC = Path(__file__).parent / "static"


def _make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # silence default logging
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path in ("/", "/index.html"):
                html = (_STATIC / "index.html").read_bytes()
                self._send(200, html, "text/html; charset=utf-8")
            elif self.path.startswith("/api/snapshot"):
                body = json.dumps(app.snapshot(), default=str).encode()
                self._send(200, body, "application/json")
            elif self.path.startswith("/api/health"):
                self._send(200, b'{"ok":true}', "application/json")
            else:
                self._send(404, b"not found", "text/plain")

    return Handler


async def serve(app, host: str = "127.0.0.1", port: int = 8000,
                stop: asyncio.Event | None = None) -> None:
    httpd = ThreadingHTTPServer((host, port), _make_handler(app))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    print(f"AccuScan dashboard: http://{host}:{port}  (Ctrl+C to stop)")
    try:
        if stop is not None:
            await stop.wait()
        else:
            while True:
                await asyncio.sleep(3600)
    finally:
        httpd.shutdown()
        thread.join(timeout=2)
