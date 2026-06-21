"""Centralised logging configuration for ProcAI.

A rotating file handler keeps disk usage bounded; a console handler is added when
running interactively. All ProcAI modules obtain their logger via
``logging.getLogger("procai.<module>")`` so a single call to :func:`configure`
controls the whole application.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from ..config import PATHS

_CONFIGURED = False
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def configure(level: int = logging.INFO, *, console: bool | None = None) -> logging.Logger:
    """Configure the root ``procai`` logger. Idempotent.

    Parameters
    ----------
    level:
        Minimum log level for the root ProcAI logger.
    console:
        Force-enable/disable the console handler. ``None`` auto-detects a TTY.
    """
    global _CONFIGURED
    root = logging.getLogger("procai")
    if _CONFIGURED:
        root.setLevel(level)
        return root

    PATHS.ensure()
    root.setLevel(level)
    root.propagate = False

    log_file: Path = PATHS.logs_dir / "procai.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(file_handler)

    if console is None:
        console = sys.stderr is not None and sys.stderr.isatty()
    if console:
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter(_LOG_FORMAT))
        root.addHandler(stream)

    _CONFIGURED = True
    root.debug("Logging configured. Log file: %s", log_file)
    return root


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the ``procai`` namespace."""
    if not name.startswith("procai"):
        name = f"procai.{name}"
    return logging.getLogger(name)
