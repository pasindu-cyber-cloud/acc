"""Live process telemetry collection via psutil.

The collector turns the OS process table into a list of :class:`ProcessSnapshot`
objects. It is defensive and robust:

* psutil is imported lazily so the rest of ProcAI (and the test-suite) works even
  where psutil is not installed.
* Per-process access errors (common for system/root processes) are swallowed --
  ProcAI reports what it can see rather than crashing or requesting unnecessary
  privilege.
* CPU percent uses psutil's stateful per-process measurement, which requires two
  reads. The collector keeps processes "primed" between scans so CPU values are
  meaningful from the second scan onward.

Nothing here modifies, injects into, or hides any process. It is read-only
observation of data the OS already exposes to the current user.
"""

from __future__ import annotations

import os
from typing import Iterable, Optional

from .models import ProcessSnapshot
from ..utils.logging_setup import get_logger

log = get_logger("core.telemetry")

try:  # pragma: no cover - exercised only where psutil is installed
    import psutil

    _HAVE_PSUTIL = True
except Exception:  # pragma: no cover
    psutil = None  # type: ignore
    _HAVE_PSUTIL = False


def psutil_available() -> bool:
    return _HAVE_PSUTIL


class TelemetryCollector:
    """Collects process snapshots from the running OS.

    Parameters
    ----------
    collect_connections:
        Whether to enumerate per-process network connections. This can be slower
        and may require elevation for some processes; it degrades gracefully.
    """

    # Fields requested from psutil in a single pass for efficiency.
    _ATTRS = [
        "pid", "name", "username", "exe", "cmdline", "ppid", "create_time",
        "cpu_percent", "memory_info", "memory_percent", "num_threads", "status",
    ]

    def __init__(self, collect_connections: bool = True) -> None:
        self.collect_connections = collect_connections
        self._primed = False

    # ------------------------------------------------------------------ #
    def prime(self) -> None:
        """Initialise psutil CPU counters so the next scan returns real values."""
        if not _HAVE_PSUTIL:
            return
        for proc in psutil.process_iter():
            try:
                proc.cpu_percent(None)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        self._primed = True

    # ------------------------------------------------------------------ #
    def collect(self) -> list[ProcessSnapshot]:
        """Return a snapshot of all visible processes."""
        if not _HAVE_PSUTIL:
            if not getattr(self, "_warned_no_psutil", False):
                log.warning("psutil unavailable; telemetry collection returns no processes.")
                self._warned_no_psutil = True
            return []
        if not self._primed:
            self.prime()

        # Build a pid -> name map so we can resolve parent names cheaply.
        name_by_pid: dict[int, str] = {}
        raw: list[dict] = []
        for proc in psutil.process_iter(self._ATTRS):
            info = proc.info
            name_by_pid[info["pid"]] = info.get("name") or ""
            raw.append(info)

        # Per-process connection counts (one pass, best effort).
        conn_counts: dict[int, tuple[int, int, tuple[int, ...]]] = {}
        if self.collect_connections:
            conn_counts = self._collect_connection_counts()

        snapshots: list[ProcessSnapshot] = []
        for info in raw:
            snapshots.append(self._to_snapshot(info, name_by_pid, conn_counts))
        return snapshots

    # ------------------------------------------------------------------ #
    def collect_one(self, pid: int) -> Optional[ProcessSnapshot]:
        """Collect a single process by PID (for deep scan / intelligence view)."""
        if not _HAVE_PSUTIL:
            return None
        try:
            proc = psutil.Process(pid)
            with proc.oneshot():
                info = {a: None for a in self._ATTRS}
                info["pid"] = pid
                info["name"] = proc.name()
                info["username"] = _safe(proc.username)
                info["exe"] = _safe(proc.exe)
                info["cmdline"] = _safe(proc.cmdline)
                info["ppid"] = _safe(proc.ppid, default=0)
                info["create_time"] = _safe(proc.create_time, default=0.0)
                info["cpu_percent"] = _safe(proc.cpu_percent, default=0.0)
                info["memory_info"] = _safe(proc.memory_info)
                info["memory_percent"] = _safe(proc.memory_percent, default=0.0)
                info["num_threads"] = _safe(proc.num_threads, default=0)
                info["status"] = _safe(proc.status, default="running")
            name_by_pid = {pid: info["name"] or ""}
            try:
                name_by_pid[info["ppid"]] = psutil.Process(info["ppid"]).name()
            except Exception:
                pass
            conn = self._collect_connection_counts(only_pid=pid)
            return self._to_snapshot(info, name_by_pid, conn)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return None

    # ------------------------------------------------------------------ #
    def _collect_connection_counts(
        self, only_pid: Optional[int] = None
    ) -> dict[int, tuple[int, int, tuple[int, ...]]]:
        """Return pid -> (num_connections, num_remote_endpoints, listening_ports)."""
        result: dict[int, tuple[int, int, tuple[int, ...]]] = {}
        try:
            conns = psutil.net_connections(kind="inet")
        except (psutil.AccessDenied, OSError, RuntimeError):
            return result
        agg: dict[int, list] = {}
        for c in conns:
            if c.pid is None:
                continue
            if only_pid is not None and c.pid != only_pid:
                continue
            total, remotes, listening = agg.setdefault(c.pid, [0, set(), set()])
            agg[c.pid][0] = total + 1
            if c.raddr:
                remotes.add(c.raddr.ip if hasattr(c.raddr, "ip") else c.raddr[0])
            if c.status == getattr(psutil, "CONN_LISTEN", "LISTEN") and c.laddr:
                listening.add(c.laddr.port if hasattr(c.laddr, "port") else c.laddr[1])
        for pid, (total, remotes, listening) in agg.items():
            result[pid] = (total, len(remotes), tuple(sorted(listening)))
        return result

    # ------------------------------------------------------------------ #
    @staticmethod
    def _to_snapshot(
        info: dict,
        name_by_pid: dict[int, str],
        conn_counts: dict[int, tuple[int, int, tuple[int, ...]]],
    ) -> ProcessSnapshot:
        pid = info.get("pid") or 0
        ppid = info.get("ppid") or 0
        mem = info.get("memory_info")
        rss = getattr(mem, "rss", 0) if mem else 0
        cmd = info.get("cmdline") or []
        cmdline = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd or "")
        n_conn, n_remote, listening = conn_counts.get(pid, (0, 0, tuple()))
        return ProcessSnapshot(
            pid=pid,
            name=info.get("name") or "",
            username=info.get("username") or "",
            exe_path=info.get("exe") or "",
            cmdline=cmdline,
            ppid=ppid,
            parent_name=name_by_pid.get(ppid, ""),
            create_time=info.get("create_time") or 0.0,
            cpu_percent=float(info.get("cpu_percent") or 0.0),
            memory_rss=int(rss),
            memory_percent=float(info.get("memory_percent") or 0.0),
            num_threads=int(info.get("num_threads") or 0),
            num_connections=n_conn,
            num_remote_endpoints=n_remote,
            listening_ports=listening,
            status=info.get("status") or "running",
        )


def system_overview() -> dict[str, float]:
    """Return host-level resource usage for the dashboard. Empty if no psutil."""
    if not _HAVE_PSUTIL:
        return {}
    try:
        vm = psutil.virtual_memory()
        return {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_percent": vm.percent,
            "memory_total_gb": vm.total / (1024 ** 3),
            "memory_used_gb": vm.used / (1024 ** 3),
            "process_count": len(psutil.pids()),
            "boot_time": psutil.boot_time(),
        }
    except Exception:  # pragma: no cover
        return {}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default
