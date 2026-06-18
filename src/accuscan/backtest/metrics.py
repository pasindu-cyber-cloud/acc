"""Replay metrics.

Computes the research metrics requested for backtesting from a per-tick record
list produced by the replay engine.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import mathx


@dataclass
class TickRecord:
    epoch: int
    index: int
    mqs: float
    status: str            # READY | WATCH | HIGH_RISK
    deterioration: float
    alert_level: str       # INFO | WARNING | CRITICAL
    danger: bool           # ground-truth label
    has_baseline: bool


def _ready_runs(records: list[TickRecord]) -> list[int]:
    runs, cur = [], 0
    for r in records:
        if r.status == "READY":
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    return runs


def danger_onsets(records: list[TickRecord]) -> list[int]:
    onsets = []
    prev = False
    for i, r in enumerate(records):
        if r.danger and not prev:
            onsets.append(i)
        prev = r.danger
    return onsets


def danger_offsets(records: list[TickRecord]) -> list[int]:
    """Indices where danger turns back to calm (danger -> calm transition)."""
    offsets = []
    prev = False
    for i, r in enumerate(records):
        if prev and not r.danger:
            offsets.append(i)
        prev = r.danger
    return offsets


def compute_metrics(
    records: list[TickRecord],
    ready_threshold: float = 72.0,
    recovery_buffer: int = 100,
) -> dict:
    n = len(records)
    if n == 0:
        return {}

    calm = [r for r in records if not r.danger]
    bad = [r for r in records if r.danger]

    # "Steady-state" calm ticks exclude the recovery window after each danger
    # offset, because the rolling feature window is still contaminated by the
    # recent danger ticks there (the model is correctly cautious, not wrong).
    in_recovery = [False] * n
    for off in danger_offsets(records):
        for j in range(off, min(off + recovery_buffer, n)):
            in_recovery[j] = True
    steady_calm = [r for r in records if not r.danger and not in_recovery[r.index]]

    runs = _ready_runs(records)
    ready_transitions = 0
    prev = None
    for r in records:
        if r.status == "READY" and prev != "READY":
            ready_transitions += 1
        prev = r.status

    # Deterioration lead/lag: ticks from each danger onset to the first
    # WARNING/CRITICAL deterioration alert (only counted where a baseline
    # existed so deterioration could fire). Lower = faster reaction.
    onsets = danger_onsets(records)
    lead_times: list[int] = []
    for onset in onsets:
        for j in range(onset, n):
            if records[j].has_baseline and records[j].alert_level in ("WARNING", "CRITICAL"):
                lead_times.append(j - onset)
                break

    # False positive: calm tick flagged HIGH_RISK or CRITICAL alert.
    fp = sum(1 for r in calm if r.status == "HIGH_RISK" or r.alert_level == "CRITICAL")
    fp_steady = sum(
        1 for r in steady_calm if r.status == "HIGH_RISK" or r.alert_level == "CRITICAL"
    )
    # False negative: danger tick NOT flagged (not HIGH_RISK and not WARNING/CRITICAL).
    fn = sum(
        1 for r in bad
        if r.status != "HIGH_RISK" and r.alert_level not in ("WARNING", "CRITICAL")
    )

    # Threshold sensitivity: how many ticks would be READY at varying thresholds.
    sensitivity = {}
    for th in (60, 65, 70, 72, 75, 78, 80, 85):
        sensitivity[th] = sum(1 for r in records if r.mqs >= th and r.status != "HIGH_RISK")

    return {
        "ticks": n,
        "ready_signals": ready_transitions,
        "ready_tick_fraction": round(sum(1 for r in records if r.status == "READY") / n, 4),
        "readiness_persistence_avg": round(mathx.mean(runs), 2) if runs else 0.0,
        "readiness_persistence_max": max(runs) if runs else 0,
        "avg_score_favorable": round(mathx.mean([r.mqs for r in calm]), 2) if calm else 0.0,
        "avg_score_unfavorable": round(mathx.mean([r.mqs for r in bad]), 2) if bad else 0.0,
        "danger_onsets": len(onsets),
        "deterioration_lead_ticks_avg": round(mathx.mean(lead_times), 2) if lead_times else None,
        "deterioration_detected_onsets": len(lead_times),
        "false_positive_rate": round(fp / len(calm), 4) if calm else 0.0,
        "false_positive_rate_steady": round(fp_steady / len(steady_calm), 4) if steady_calm else 0.0,
        "false_negative_rate": round(fn / len(bad), 4) if bad else 0.0,
        "threshold_sensitivity_ready_ticks": sensitivity,
    }
