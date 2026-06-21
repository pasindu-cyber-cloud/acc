"""Plain data models shared across the detection pipeline.

These are deliberately dependency-free dataclasses (standard library only) so the
core engine can run, and be unit-tested, without psutil, numpy or scikit-learn.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional


class Severity(IntEnum):
    """Ordered severity levels. Higher value == more severe."""

    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @property
    def label(self) -> str:
        return self.name.capitalize()

    @classmethod
    def from_name(cls, name: str) -> "Severity":
        try:
            return cls[name.strip().upper()]
        except KeyError:
            return cls.INFO

    @classmethod
    def from_score(cls, score: float) -> "Severity":
        """Map a 0-100 risk score to a severity band."""
        if score >= 85:
            return cls.CRITICAL
        if score >= 65:
            return cls.HIGH
        if score >= 45:
            return cls.MEDIUM
        if score >= 25:
            return cls.LOW
        return cls.INFO


@dataclass
class ProcessSnapshot:
    """A single point-in-time observation of one process.

    All resource fields are best-effort; collection on a live OS frequently hits
    permission errors for system processes, so missing values use sensible
    defaults rather than raising.
    """

    pid: int
    name: str
    timestamp: float = field(default_factory=time.time)

    # Identity / lineage
    username: str = ""
    exe_path: str = ""
    cmdline: str = ""
    ppid: int = 0
    parent_name: str = ""
    create_time: float = 0.0

    # Resource telemetry
    cpu_percent: float = 0.0
    memory_rss: int = 0            # bytes
    memory_percent: float = 0.0
    num_threads: int = 0
    num_handles: int = 0           # Windows handles / open files
    io_read_bytes: int = 0
    io_write_bytes: int = 0

    # Network
    num_connections: int = 0
    num_remote_endpoints: int = 0
    listening_ports: tuple[int, ...] = field(default_factory=tuple)

    # Reputation (filled by reputation module; advisory)
    is_signed: Optional[bool] = None      # None == unknown / not checked
    signer: str = ""
    in_suspicious_dir: bool = False
    is_startup_persistent: bool = False
    status: str = "running"

    @property
    def lifetime_seconds(self) -> float:
        if not self.create_time:
            return 0.0
        return max(0.0, self.timestamp - self.create_time)

    @property
    def memory_mb(self) -> float:
        return self.memory_rss / (1024 * 1024)

    def identity_key(self) -> str:
        """Stable key for baseline tracking (per executable, not per PID)."""
        return (self.exe_path or self.name).lower()


@dataclass
class RuleHit:
    """One transparent heuristic that fired for a process."""

    rule_id: str
    title: str
    points: float                 # contribution toward the rule score (0-100 scale)
    severity: Severity
    explanation: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class MLResult:
    """Output of the machine-learning classifier for one process."""

    available: bool = False
    model_name: str = ""
    is_suspicious: bool = False
    probability: float = 0.0      # P(suspicious), 0-1
    confidence: float = 0.0       # |p - 0.5| * 2, 0-1
    top_features: list[tuple[str, float]] = field(default_factory=list)


@dataclass
class BaselineDeviation:
    """Z-score deviation of the current snapshot from the learned baseline."""

    available: bool = False
    samples: int = 0
    z_scores: dict[str, float] = field(default_factory=dict)
    max_abs_z: float = 0.0
    deviating_metrics: list[str] = field(default_factory=list)


@dataclass
class DetectionResult:
    """Final fused verdict produced by the hybrid engine for one snapshot."""

    snapshot: ProcessSnapshot
    risk_score: float                       # 0-100
    severity: Severity
    confidence: float                       # 0-1
    should_alert: bool
    rule_score: float = 0.0
    rule_hits: list[RuleHit] = field(default_factory=list)
    ml: MLResult = field(default_factory=MLResult)
    deviation: BaselineDeviation = field(default_factory=BaselineDeviation)
    components: dict[str, float] = field(default_factory=dict)  # named sub-scores
    reasons: list[str] = field(default_factory=list)
    suppressed: bool = False
    recommended_action: str = ""


@dataclass
class Alert:
    """A persisted alert raised for a suspicious process."""

    id: Optional[int] = None
    timestamp: float = field(default_factory=time.time)
    pid: int = 0
    process_name: str = ""
    exe_path: str = ""
    username: str = ""
    risk_score: float = 0.0
    severity: Severity = Severity.INFO
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    rule_hits: list[str] = field(default_factory=list)
    ml_probability: float = 0.0
    recommended_action: str = ""
    acknowledged: bool = False
    resolution: str = ""          # e.g. "" | "dismissed" | "terminated" | "allowlisted"

    @classmethod
    def from_detection(cls, result: DetectionResult) -> "Alert":
        s = result.snapshot
        return cls(
            timestamp=s.timestamp,
            pid=s.pid,
            process_name=s.name,
            exe_path=s.exe_path,
            username=s.username,
            risk_score=round(result.risk_score, 2),
            severity=result.severity,
            confidence=round(result.confidence, 3),
            reasons=list(result.reasons),
            rule_hits=[h.rule_id for h in result.rule_hits],
            ml_probability=round(result.ml.probability, 3),
            recommended_action=result.recommended_action,
        )


@dataclass
class ModelMetadata:
    """Metadata describing a trained ML model on disk."""

    name: str
    algorithm: str
    trained_at: float
    n_samples: int
    n_features: int
    feature_names: list[str]
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    notes: str = ""
