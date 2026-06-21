"""Offline, rule-based plain-language explanations (no network, no AI keys).

This is the default Proc Assistant backend and the source of truth for *why*
ProcAI reached a verdict. It deterministically converts a
:class:`DetectionResult` into:

* a short headline,
* a plain-English behaviour summary,
* the concrete evidence (rule hits, ML view, baseline deviation),
* prioritised recommended next steps, and
* a guided investigation checklist.

Because it is deterministic and offline it is auditable, reproducible and
privacy-preserving -- exactly what a dissertation/portfolio project should be
able to demonstrate without depending on a third-party model.
"""

from __future__ import annotations

from ..core.models import DetectionResult, Severity


def _risk_phrase(sev: Severity) -> str:
    return {
        Severity.CRITICAL: "a critical-risk process that needs immediate attention",
        Severity.HIGH: "a high-risk process you should review soon",
        Severity.MEDIUM: "a medium-risk process worth keeping an eye on",
        Severity.LOW: "a low-risk anomaly",
        Severity.INFO: "normal-looking behaviour",
    }[sev]


def summarise_alert(result: DetectionResult) -> str:
    """One-line headline for lists/notifications."""
    s = result.snapshot
    return (
        f"{s.name} (PID {s.pid}) is {_risk_phrase(result.severity)} "
        f"- risk {result.risk_score:.0f}/100, confidence {result.confidence:.0%}."
    )


def explain_detection(result: DetectionResult) -> str:
    """A full, readable, multi-section explanation."""
    s = result.snapshot
    lines: list[str] = []

    lines.append(f"## {s.name} (PID {s.pid})")
    lines.append("")
    lines.append(f"**Verdict:** {result.severity.label} risk "
                 f"({result.risk_score:.0f}/100), confidence {result.confidence:.0%}.")
    lines.append("")

    # Behaviour summary
    lines.append("**What this process is doing**")
    lines.append(
        f"- CPU: {s.cpu_percent:.0f}%  |  Memory: {s.memory_mb:.0f} MB "
        f"({s.memory_percent:.0f}% of RAM)  |  Threads: {s.num_threads}"
    )
    lines.append(
        f"- Network: {s.num_connections} connections to "
        f"{s.num_remote_endpoints} distinct hosts"
    )
    if s.exe_path:
        lines.append(f"- Location: {s.exe_path}")
    if s.parent_name:
        lines.append(f"- Started by: {s.parent_name} (PID {s.ppid})")
    sign = (
        "unsigned" if s.is_signed is False
        else ("signed" + (f" by {s.signer}" if s.signer else "") if s.is_signed else "unknown signature")
    )
    lines.append(f"- Code signature: {sign}")
    if s.lifetime_seconds:
        lines.append(f"- Running for: {s.lifetime_seconds / 60:.1f} minutes")
    lines.append("")

    # Why flagged
    lines.append("**Why ProcAI flagged it**")
    if result.rule_hits:
        for h in result.rule_hits:
            lines.append(f"- {h.title} (+{h.points:.0f}): {h.explanation}")
    else:
        lines.append("- No individual rules fired strongly.")
    if result.ml.available:
        verdict = "suspicious" if result.ml.is_suspicious else "normal"
        lines.append(
            f"- ML model ({result.ml.model_name}): classified as **{verdict}** "
            f"(P(suspicious)={result.ml.probability:.0%})."
        )
        if result.ml.top_features:
            feats = ", ".join(f"{n}" for n, _ in result.ml.top_features[:3])
            lines.append(f"  - Most influential features: {feats}.")
    if result.deviation.available and result.deviation.deviating_metrics:
        lines.append(
            f"- Baseline deviation: unusual on "
            f"{', '.join(result.deviation.deviating_metrics)} "
            f"(max Z-score {result.deviation.max_abs_z:.1f})."
        )
    lines.append("")

    # Score breakdown
    comp = result.components
    if comp and "rule_score" in comp:
        lines.append("**How the score was combined**")
        lines.append(
            f"- Rule score {comp.get('rule_score', 0):.0f} (weight {comp.get('w_rules', 0):.0%}), "
            f"ML score {comp.get('ml_score', 0):.0f} (weight {comp.get('w_ml', 0):.0%}), "
            f"baseline score {comp.get('baseline_score', 0):.0f} (weight {comp.get('w_baseline', 0):.0%})."
        )
        lines.append("")

    # Recommendation
    lines.append("**Recommended action**")
    lines.append(f"- {result.recommended_action}")
    if result.suppressed:
        lines.append("- Note: this process is on your trusted allowlist, so no alert was raised.")
    lines.append("")

    lines.append("_Explanation generated offline by ProcAI. No data left your machine._")
    return "\n".join(lines)


def investigation_guide(result: DetectionResult) -> list[str]:
    """A prioritised checklist tailored to the indicators that fired."""
    s = result.snapshot
    steps: list[str] = []
    rule_ids = {h.rule_id for h in result.rule_hits}

    steps.append(f"Confirm whether you recognise '{s.name}' and expect it to be running now.")
    if s.exe_path:
        steps.append(f"Verify the executable location is legitimate: {s.exe_path}")
    if "unsigned" in rule_ids or s.is_signed is False:
        steps.append("Check the publisher/signature; treat unsigned binaries with caution.")
    if {"net_many", "net_elevated"} & rule_ids:
        steps.append("Review the remote addresses it is connecting to; look for unknown IPs/domains.")
    if {"lineage_office_shell", "lineage_unusual_shell"} & rule_ids:
        steps.append(f"Investigate the parent process '{s.parent_name}' - why did it start a shell?")
    if {"cpu_high", "thread_storm", "mem_high"} & rule_ids:
        steps.append("Determine whether the resource usage matches the program's normal workload.")
    if "path_suspicious" in rule_ids:
        steps.append("Be cautious: software rarely runs legitimately from Temp/Downloads folders.")
    steps.append("If unsure, leave monitoring on and watch whether the behaviour persists or escalates.")
    steps.append(
        "Only terminate the process after confirming it is not a needed system task "
        "(ProcAI requires explicit confirmation before terminating)."
    )
    return steps
