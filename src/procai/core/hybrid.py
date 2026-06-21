"""Hybrid anomaly engine: fuse rules + ML + baseline into one verdict.

This is the decision core of ProcAI. For each :class:`ProcessSnapshot` it:

1. runs the transparent rule engine          -> ``rule_score`` (0-100)
2. asks the ML classifier                     -> ``ml_score`` (0-100, from P(susp))
3. computes baseline Z-score deviation        -> ``baseline_score`` (0-100)
4. fuses them into a weighted ``risk_score``  -> 0-100
5. derives a ``confidence`` and a ``severity``
6. applies sensitivity profile + allow/block lists + suppression to decide
   whether to ``should_alert``.

Fusion weights
--------------
The ML weight comes from the active :class:`SensitivityProfile`. The remaining
weight is split between rules and baseline. When a component is unavailable
(no model yet, or an immature baseline) its weight is redistributed to the
available components, so the engine always produces a sensible score.

Everything is transparent: ``DetectionResult.components`` records each sub-score
and weight, and ``reasons`` lists the human-readable drivers, so the GUI and the
Proc Assistant can fully explain the verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .baseline import BaselineManager
from .features import extract
from .ml import MLClassifier
from .models import (
    BaselineDeviation,
    DetectionResult,
    MLResult,
    ProcessSnapshot,
    Severity,
)
from .rules import RuleEngine
from ..config import SensitivityProfile, Settings
from ..utils.logging_setup import get_logger

log = get_logger("core.hybrid")


def _baseline_score(dev: BaselineDeviation) -> float:
    """Map baseline deviation to a 0-100 sub-score.

    Below |Z|=3 contributes nothing; above that it ramps up, and additional
    deviating metrics add a corroboration bonus.
    """
    if not dev.available or dev.max_abs_z < 3.0:
        return 0.0
    intensity = min(1.0, (dev.max_abs_z - 3.0) / 7.0)            # 3..10 -> 0..1
    breadth = min(1.0, len(dev.deviating_metrics) / 4.0)         # up to 4 metrics
    return round(100.0 * (0.7 * intensity + 0.3 * breadth), 2)


@dataclass
class HybridConfig:
    """Resolved tunables for one evaluation (derived from Settings)."""

    profile: SensitivityProfile
    ml_weight: float
    threshold: float
    enable_ml: bool
    suppress_trusted: bool
    allowlist: frozenset[str]
    blocklist: frozenset[str]
    learning_mode: bool

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        learning_mode: bool = False,
        extra_allow: Optional[list[str]] = None,
        extra_block: Optional[list[str]] = None,
    ) -> "HybridConfig":
        allow = {p.lower() for p in settings.allowlist} | {
            p.lower() for p in (extra_allow or [])
        }
        block = {p.lower() for p in settings.blocklist} | {
            p.lower() for p in (extra_block or [])
        }
        return cls(
            profile=settings.sensitivity,
            ml_weight=settings.sensitivity.ml_weight if settings.enable_ml else 0.0,
            threshold=settings.sensitivity.alert_threshold,
            enable_ml=settings.enable_ml,
            suppress_trusted=settings.suppress_trusted,
            allowlist=frozenset(allow),
            blocklist=frozenset(block),
            learning_mode=learning_mode,
        )


class HybridEngine:
    """Fuses the three detectors into a final verdict."""

    def __init__(
        self,
        rule_engine: RuleEngine,
        baseline: BaselineManager,
        classifier: Optional[MLClassifier] = None,
    ) -> None:
        self.rules = rule_engine
        self.baseline = baseline
        self.classifier = classifier

    # ------------------------------------------------------------------ #
    def _matches_list(self, snap: ProcessSnapshot, patterns: frozenset[str]) -> bool:
        if not patterns:
            return False
        name = (snap.name or "").lower()
        exe = (snap.exe_path or "").lower()
        for pat in patterns:
            if pat and (pat == name or pat == exe or pat in exe):
                return True
        return False

    # ------------------------------------------------------------------ #
    def evaluate(self, snap: ProcessSnapshot, config: HybridConfig) -> DetectionResult:
        # --- 1. blocklist short-circuit (always alert) ---
        if self._matches_list(snap, config.blocklist):
            return self._blocked_result(snap)

        # --- 2. run detectors ---
        dev = self.baseline.deviation(snap)
        rule_eval = self.rules.evaluate(snap, dev)
        ml_result = MLResult(available=False)
        if config.enable_ml and self.classifier is not None and self.classifier.is_loaded():
            ml_result = self.classifier.predict(snap)

        rule_score = rule_eval.score
        ml_score = ml_result.probability * 100.0 if ml_result.available else 0.0
        base_score = _baseline_score(dev)

        # --- 3. resolve weights, redistributing for unavailable components ---
        w_ml = config.ml_weight if ml_result.available else 0.0
        remaining = 1.0 - w_ml
        # Split remaining between rules (dominant) and baseline.
        if dev.available:
            w_rules = remaining * 0.65
            w_base = remaining * 0.35
        else:
            w_rules = remaining
            w_base = 0.0
        total_w = w_ml + w_rules + w_base or 1.0
        w_ml, w_rules, w_base = w_ml / total_w, w_rules / total_w, w_base / total_w

        risk = w_ml * ml_score + w_rules * rule_score + w_base * base_score

        # Corroboration boost: if 2+ independent detectors strongly agree, nudge up.
        strong = sum(
            1 for v in (rule_score >= 50, ml_score >= 60, base_score >= 50) if v
        )
        if strong >= 2:
            risk = min(100.0, risk + 6.0 * (strong - 1))

        risk = round(max(0.0, min(100.0, risk)), 2)
        severity = Severity.from_score(risk)
        confidence = self._confidence(rule_eval.hits, ml_result, dev, strong)

        reasons = self._reasons(rule_eval, ml_result, dev)
        result = DetectionResult(
            snapshot=snap,
            risk_score=risk,
            severity=severity,
            confidence=round(confidence, 3),
            should_alert=False,  # decided below
            rule_score=rule_score,
            rule_hits=rule_eval.hits,
            ml=ml_result,
            deviation=dev,
            components={
                "rule_score": rule_score,
                "ml_score": round(ml_score, 2),
                "baseline_score": base_score,
                "w_rules": round(w_rules, 3),
                "w_ml": round(w_ml, 3),
                "w_baseline": round(w_base, 3),
            },
            reasons=reasons,
            recommended_action=self._recommend(severity),
        )

        # --- 4. allow/suppress + threshold/learning decision ---
        self._decide_alert(result, snap, config)
        return result

    # ------------------------------------------------------------------ #
    def _decide_alert(
        self, result: DetectionResult, snap: ProcessSnapshot, config: HybridConfig
    ) -> None:
        # Trusted allowlist: never alert (but still scored/visible).
        if config.suppress_trusted and self._matches_list(snap, config.allowlist):
            result.suppressed = True
            result.should_alert = False
            result.reasons.insert(0, "Process is on the trusted allowlist; alert suppressed.")
            return
        above = result.risk_score >= config.threshold
        if config.learning_mode:
            # During learning we observe but hold back deviation-driven alerts,
            # only alerting on strong, unambiguous rule signals.
            result.should_alert = above and result.rule_score >= 60.0
            if above and not result.should_alert:
                result.reasons.insert(
                    0, "Learning mode active: alert held while baseline is established."
                )
        else:
            result.should_alert = above

    # ------------------------------------------------------------------ #
    def _blocked_result(self, snap: ProcessSnapshot) -> DetectionResult:
        return DetectionResult(
            snapshot=snap,
            risk_score=100.0,
            severity=Severity.CRITICAL,
            confidence=1.0,
            should_alert=True,
            rule_score=100.0,
            reasons=["Process matches a user-defined blocklist entry."],
            components={"blocklist": 1.0},
            recommended_action="Investigate immediately; this item was explicitly blocklisted.",
        )

    # ------------------------------------------------------------------ #
    @staticmethod
    def _confidence(hits, ml: MLResult, dev: BaselineDeviation, strong: int) -> float:
        """Confidence in the verdict (0-1), distinct from the risk magnitude.

        Driven by how decisive the ML model is, how mature the baseline is, how
        many rules fired, and how many detectors agree.
        """
        parts: list[float] = []
        if ml.available:
            parts.append(ml.confidence)
        if dev.available:
            parts.append(min(1.0, dev.samples / 30.0))
        parts.append(min(1.0, len(hits) / 4.0))
        base = sum(parts) / len(parts) if parts else 0.3
        base += 0.1 * max(0, strong - 1)
        return max(0.0, min(1.0, base))

    # ------------------------------------------------------------------ #
    @staticmethod
    def _reasons(rule_eval, ml: MLResult, dev: BaselineDeviation) -> list[str]:
        reasons = [f"{h.title}: {h.explanation}" for h in rule_eval.hits]
        if ml.available:
            verdict = "suspicious" if ml.is_suspicious else "normal"
            reasons.append(
                f"ML model ({ml.model_name}) classifies this process as {verdict} "
                f"(P(suspicious)={ml.probability:.0%}, confidence {ml.confidence:.0%})."
            )
        if dev.available and dev.deviating_metrics:
            reasons.append(
                "Statistical deviation from this program's baseline on "
                f"{', '.join(dev.deviating_metrics)} (max Z={dev.max_abs_z:.1f})."
            )
        if not reasons:
            reasons.append("No suspicious indicators detected; behaviour looks normal.")
        return reasons

    # ------------------------------------------------------------------ #
    @staticmethod
    def _recommend(severity: Severity) -> str:
        return {
            Severity.CRITICAL: (
                "Investigate now. Review the process lineage and network activity, "
                "and consider terminating it after confirming it is not a needed system task."
            ),
            Severity.HIGH: (
                "Review this process soon. Check its origin, signature and connections; "
                "use the Proc Assistant for a guided explanation."
            ),
            Severity.MEDIUM: (
                "Keep an eye on this process. If it is unfamiliar, inspect its details."
            ),
            Severity.LOW: "Low-risk anomaly. No action needed unless it recurs.",
            Severity.INFO: "Informational only. No action needed.",
        }[severity]
