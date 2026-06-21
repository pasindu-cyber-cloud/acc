"""Transparent rule-based scoring engine.

Every rule is a small, named, fully-explainable heuristic. A rule inspects a
:class:`ProcessSnapshot` (optionally with its baseline deviation) and, if it
fires, returns a :class:`RuleHit` carrying:

* the points it contributes,
* a human-readable title and explanation, and
* the concrete evidence (the values that triggered it).

This transparency is a core design goal: a security analyst (or a dissertation
examiner) can always see *exactly why* a process was flagged. Rules are advisory
signals -- the hybrid engine combines them with ML and baseline deviation before
deciding whether to alert.

The raw points are summed and squashed into a 0-100 ``rule_score`` so that any
single rule cannot by itself saturate the score, while several corroborating
weak signals still add up.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Optional

from .models import BaselineDeviation, ProcessSnapshot, RuleHit, Severity

# Processes that legitimately spawn shells/children, used to reduce lineage FPs.
_KNOWN_SHELL_PARENTS = {
    "cmd.exe", "powershell.exe", "pwsh.exe", "explorer.exe", "bash", "sh",
    "code.exe", "windowsterminal.exe", "conhost.exe", "python.exe", "py.exe",
}
# Office-style parents spawning a shell is a classic suspicious lineage.
_OFFICE_PARENTS = {
    "winword.exe", "excel.exe", "powerpnt.exe", "outlook.exe", "msaccess.exe",
}
_SHELL_CHILDREN = {"cmd.exe", "powershell.exe", "pwsh.exe", "wscript.exe", "cscript.exe", "mshta.exe"}


@dataclass
class Rule:
    """A single heuristic."""

    rule_id: str
    title: str
    severity: Severity
    func: Callable[[ProcessSnapshot, Optional[BaselineDeviation]], Optional[RuleHit]]


# --------------------------------------------------------------------------- #
# Individual rule implementations
# --------------------------------------------------------------------------- #
def _r_high_cpu(s: ProcessSnapshot, _d) -> Optional[RuleHit]:
    if s.cpu_percent >= 85:
        return RuleHit(
            "cpu_high", "Sustained very high CPU usage", 22.0, Severity.MEDIUM,
            f"CPU usage is {s.cpu_percent:.0f}%, which is unusually high and can "
            "indicate cryptomining, brute-forcing or a runaway/abused process.",
            {"cpu_percent": round(s.cpu_percent, 1)},
        )
    if s.cpu_percent >= 60:
        return RuleHit(
            "cpu_elevated", "Elevated CPU usage", 10.0, Severity.LOW,
            f"CPU usage is {s.cpu_percent:.0f}%.",
            {"cpu_percent": round(s.cpu_percent, 1)},
        )
    return None


def _r_high_memory(s: ProcessSnapshot, _d) -> Optional[RuleHit]:
    if s.memory_percent >= 40 or s.memory_mb >= 2048:
        return RuleHit(
            "mem_high", "High memory footprint", 16.0, Severity.MEDIUM,
            f"Process is using {s.memory_mb:.0f} MB ({s.memory_percent:.0f}% of RAM), "
            "which may indicate data staging or a memory-heavy payload.",
            {"memory_mb": round(s.memory_mb, 1), "memory_percent": round(s.memory_percent, 1)},
        )
    return None


def _r_thread_storm(s: ProcessSnapshot, _d) -> Optional[RuleHit]:
    if s.num_threads >= 400:
        return RuleHit(
            "thread_storm", "Abnormally high thread count", 18.0, Severity.MEDIUM,
            f"Process holds {s.num_threads} threads; very high counts can indicate "
            "injection, parallel scanning or resource abuse.",
            {"num_threads": s.num_threads},
        )
    if s.num_threads >= 200:
        return RuleHit(
            "thread_elevated", "Elevated thread count", 8.0, Severity.LOW,
            f"Process holds {s.num_threads} threads.", {"num_threads": s.num_threads},
        )
    return None


def _r_network_beacon(s: ProcessSnapshot, _d) -> Optional[RuleHit]:
    if s.num_connections >= 50 or s.num_remote_endpoints >= 30:
        return RuleHit(
            "net_many", "Large number of network connections", 20.0, Severity.MEDIUM,
            f"Process has {s.num_connections} connections to "
            f"{s.num_remote_endpoints} distinct remote endpoints, which can indicate "
            "scanning, beaconing or C2-style traffic.",
            {"connections": s.num_connections, "remote_endpoints": s.num_remote_endpoints},
        )
    if s.num_remote_endpoints >= 12:
        return RuleHit(
            "net_elevated", "Several distinct remote endpoints", 9.0, Severity.LOW,
            f"Process is talking to {s.num_remote_endpoints} distinct remote hosts.",
            {"remote_endpoints": s.num_remote_endpoints},
        )
    return None


def _r_suspicious_path(s: ProcessSnapshot, _d) -> Optional[RuleHit]:
    if s.in_suspicious_dir:
        return RuleHit(
            "path_suspicious", "Executable runs from an unusual location", 16.0, Severity.MEDIUM,
            "The executable is located in a directory commonly abused by malware "
            f"(e.g. Temp/Downloads/Public): {s.exe_path or 'unknown'}.",
            {"exe_path": s.exe_path},
        )
    return None


def _r_unsigned(s: ProcessSnapshot, _d) -> Optional[RuleHit]:
    if s.is_signed is False:
        pts = 18.0 if s.in_suspicious_dir else 12.0
        return RuleHit(
            "unsigned", "Unsigned executable", pts, Severity.MEDIUM,
            "The executable is not Authenticode-signed. Most legitimate software is "
            "signed; unsigned binaries warrant closer inspection.",
            {"is_signed": False, "exe_path": s.exe_path},
        )
    return None


def _r_lineage(s: ProcessSnapshot, _d) -> Optional[RuleHit]:
    parent = (s.parent_name or "").lower()
    child = (s.name or "").lower()
    if parent in _OFFICE_PARENTS and child in _SHELL_CHILDREN:
        return RuleHit(
            "lineage_office_shell", "Office application spawned a shell", 26.0, Severity.HIGH,
            f"'{s.parent_name}' launched '{s.name}'. Document applications spawning "
            "command interpreters is a well-known malicious-macro pattern.",
            {"parent": s.parent_name, "child": s.name},
        )
    if child in _SHELL_CHILDREN and parent and parent not in _KNOWN_SHELL_PARENTS:
        return RuleHit(
            "lineage_unusual_shell", "Shell launched by an unusual parent", 12.0, Severity.LOW,
            f"'{s.name}' was started by '{s.parent_name}', an uncommon parent for a "
            "command interpreter.",
            {"parent": s.parent_name, "child": s.name},
        )
    return None


def _r_short_lived_burst(s: ProcessSnapshot, _d) -> Optional[RuleHit]:
    if 0 < s.lifetime_seconds <= 30 and (s.cpu_percent >= 60 or s.memory_mb >= 800):
        return RuleHit(
            "young_resource_burst", "Very new process consuming heavy resources",
            14.0, Severity.MEDIUM,
            f"Process is only {s.lifetime_seconds:.0f}s old but already at "
            f"{s.cpu_percent:.0f}% CPU / {s.memory_mb:.0f} MB.",
            {"lifetime_s": round(s.lifetime_seconds, 1), "cpu": round(s.cpu_percent, 1)},
        )
    return None


def _r_startup_persistence(s: ProcessSnapshot, _d) -> Optional[RuleHit]:
    if s.is_startup_persistent and (s.is_signed is False or s.in_suspicious_dir):
        return RuleHit(
            "persist_suspicious", "Auto-start entry for a low-reputation executable",
            14.0, Severity.MEDIUM,
            "This executable is configured to start automatically and is also "
            "unsigned or located in an unusual directory.",
            {"startup": True, "is_signed": s.is_signed, "suspicious_dir": s.in_suspicious_dir},
        )
    return None


def _r_baseline_deviation(s: ProcessSnapshot, d: Optional[BaselineDeviation]) -> Optional[RuleHit]:
    if d is None or not d.available or not d.deviating_metrics:
        return None
    # Scale points by how many metrics deviate and how strongly.
    pts = min(24.0, 6.0 * len(d.deviating_metrics) + 1.5 * (d.max_abs_z - 3.0))
    return RuleHit(
        "baseline_deviation", "Behaviour deviates from this program's baseline",
        round(max(pts, 6.0), 1), Severity.MEDIUM,
        "Compared with its own learned baseline, this process is behaving unusually "
        f"on {', '.join(d.deviating_metrics)} (max Z-score {d.max_abs_z:.1f}).",
        {"deviating_metrics": d.deviating_metrics, "max_abs_z": d.max_abs_z},
    )


# Registry of all rules (order only affects display).
ALL_RULES: list[Rule] = [
    Rule("cpu", "CPU usage", Severity.MEDIUM, _r_high_cpu),
    Rule("memory", "Memory usage", Severity.MEDIUM, _r_high_memory),
    Rule("threads", "Thread count", Severity.MEDIUM, _r_thread_storm),
    Rule("network", "Network activity", Severity.MEDIUM, _r_network_beacon),
    Rule("path", "Executable path", Severity.MEDIUM, _r_suspicious_path),
    Rule("signature", "Code signing", Severity.MEDIUM, _r_unsigned),
    Rule("lineage", "Parent-child lineage", Severity.HIGH, _r_lineage),
    Rule("lifetime", "Process lifetime", Severity.MEDIUM, _r_short_lived_burst),
    Rule("persistence", "Startup persistence", Severity.MEDIUM, _r_startup_persistence),
    Rule("baseline", "Baseline deviation", Severity.MEDIUM, _r_baseline_deviation),
]


@dataclass
class RuleEvaluation:
    """Result of running the rule engine over one snapshot."""

    score: float                      # 0-100
    raw_points: float
    hits: list[RuleHit]


class RuleEngine:
    """Evaluates all rules and squashes raw points into a 0-100 score."""

    def __init__(self, rules: Optional[list[Rule]] = None) -> None:
        self.rules = rules if rules is not None else ALL_RULES

    def evaluate(
        self, snap: ProcessSnapshot, deviation: Optional[BaselineDeviation] = None
    ) -> RuleEvaluation:
        hits: list[RuleHit] = []
        for rule in self.rules:
            try:
                hit = rule.func(snap, deviation)
            except Exception:  # a faulty rule must never crash detection
                hit = None
            if hit is not None:
                hits.append(hit)
        raw = sum(h.points for h in hits)
        score = self._squash(raw)
        return RuleEvaluation(score=round(score, 2), raw_points=round(raw, 2), hits=hits)

    @staticmethod
    def _squash(raw_points: float) -> float:
        """Map unbounded raw points to 0-100 with diminishing returns.

        Uses a saturating curve: many corroborating signals approach but never
        exceed 100, and ~40 raw points already lands around 63.
        """
        if raw_points <= 0:
            return 0.0
        return 100.0 * (1.0 - math.exp(-raw_points / 40.0))
