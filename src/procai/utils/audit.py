"""Tamper-evident audit log of user and system actions.

ProcAI is transparent security software: every privileged or state-changing
action (start/stop monitoring, terminate a process, change settings, enable the
AI assistant, retrain a model, etc.) is recorded.

The audit log is a hash-chained append-only file. Each entry stores the SHA-256
of the previous entry, so any after-the-fact deletion or edit breaks the chain
and is detectable via :func:`verify`. This is *evidence integrity*, not secrecy
-- the log is plain JSON-lines that the user can read at any time.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Iterator

from ..config import PATHS

_GENESIS = "0" * 64
_lock = threading.Lock()


def _hash_entry(prev_hash: str, payload: dict[str, Any]) -> str:
    serialised = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{prev_hash}{serialised}".encode("utf-8")).hexdigest()


def _last_hash(path: Path) -> str:
    if not path.exists():
        return _GENESIS
    last = _GENESIS
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    last = json.loads(line).get("hash", last)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return _GENESIS
    return last


def record(action: str, detail: dict[str, Any] | None = None, *, actor: str = "user") -> None:
    """Append an audit entry.

    Parameters
    ----------
    action:
        Short action identifier, e.g. ``"monitoring.start"`` or
        ``"process.terminate"``.
    detail:
        Optional structured context (PID, process name, old/new setting...).
    actor:
        ``"user"``, ``"service"`` or ``"system"``.
    """
    path = PATHS.audit_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        prev = _last_hash(path)
        payload = {
            "ts": time.time(),
            "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "actor": actor,
            "action": action,
            "detail": detail or {},
            "prev": prev,
        }
        payload["hash"] = _hash_entry(prev, payload)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, separators=(",", ":")) + "\n")


def read_all(path: Path | None = None) -> list[dict[str, Any]]:
    """Return every audit entry as a list of dicts (oldest first)."""
    path = path or PATHS.audit_path
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def iter_entries(path: Path | None = None) -> Iterator[dict[str, Any]]:
    yield from read_all(path)


def verify(path: Path | None = None) -> tuple[bool, int]:
    """Verify the hash chain.

    Returns ``(ok, index)``. ``ok`` is ``True`` if the chain is intact; if not,
    ``index`` is the position of the first broken/altered entry.
    """
    path = path or PATHS.audit_path
    prev = _GENESIS
    for idx, entry in enumerate(read_all(path)):
        stored_hash = entry.get("hash")
        recomputed = dict(entry)
        recomputed.pop("hash", None)
        if entry.get("prev") != prev or _hash_entry(prev, recomputed) != stored_hash:
            return False, idx
        prev = stored_hash
    return True, -1
