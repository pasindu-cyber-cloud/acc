"""Export alerts and process history to CSV / PDF.

CSV export uses only the standard library and is always available. PDF export
uses reportlab when installed (``pip install procai[reports]``); if it is not
present :func:`pdf_available` returns False and the GUI offers CSV only.

Exports are written to the per-user reports directory by default and the path is
returned so the caller can reveal it to the user.
"""

from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Optional, Sequence

from ..config import PATHS
from ..core.models import Alert
from ..utils import audit
from ..utils.logging_setup import get_logger

log = get_logger("reports.exporter")

try:  # pragma: no cover - only where the reports extra is installed
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    )

    _HAVE_REPORTLAB = True
except Exception:  # pragma: no cover
    _HAVE_REPORTLAB = False


def pdf_available() -> bool:
    return _HAVE_REPORTLAB


def _timestamp_name(prefix: str, ext: str) -> Path:
    PATHS.ensure()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return PATHS.reports_dir / f"{prefix}_{stamp}.{ext}"


# --------------------------------------------------------------------------- #
# CSV
# --------------------------------------------------------------------------- #
def export_alerts_csv(alerts: Sequence[Alert], path: Optional[Path] = None) -> Path:
    path = path or _timestamp_name("procai_alerts", "csv")
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "timestamp", "pid", "process_name", "exe_path", "username",
            "risk_score", "severity", "confidence", "ml_probability",
            "reasons", "rule_hits", "recommended_action",
            "acknowledged", "resolution",
        ])
        for a in alerts:
            writer.writerow([
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(a.timestamp)),
                a.pid, a.process_name, a.exe_path, a.username,
                f"{a.risk_score:.2f}", a.severity.label, f"{a.confidence:.3f}",
                f"{a.ml_probability:.3f}", " | ".join(a.reasons),
                ", ".join(a.rule_hits), a.recommended_action,
                "yes" if a.acknowledged else "no", a.resolution,
            ])
    audit.record("report.export", {"format": "csv", "kind": "alerts", "count": len(alerts)})
    log.info("Exported %d alerts to %s", len(alerts), path)
    return path


def export_process_history_csv(rows: Sequence[dict], path: Optional[Path] = None) -> Path:
    path = path or _timestamp_name("procai_process_history", "csv")
    fields = [
        "ts", "pid", "name", "exe_path", "username", "ppid", "parent_name",
        "cpu_percent", "memory_rss", "memory_percent", "num_threads",
        "num_connections", "is_signed", "in_suspicious_dir", "risk_score", "severity",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            row = dict(r)
            if "ts" in row and isinstance(row["ts"], (int, float)):
                row["ts"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(row["ts"]))
            writer.writerow(row)
    audit.record("report.export", {"format": "csv", "kind": "process_history", "count": len(rows)})
    return path


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def export_alerts_pdf(
    alerts: Sequence[Alert],
    path: Optional[Path] = None,
    *,
    title: str = "ProcAI Security Report",
    summary: Optional[dict] = None,
) -> Path:
    if not _HAVE_REPORTLAB:
        raise RuntimeError("reportlab is not installed (pip install procai[reports]).")
    path = path or _timestamp_name("procai_report", "pdf")

    doc = SimpleDocTemplate(str(path), pagesize=A4, title=title)
    styles = getSampleStyleSheet()
    accent = ParagraphStyle("accent", parent=styles["Normal"], textColor=colors.HexColor("#1976D2"))
    story = []

    story.append(Paragraph(title, styles["Title"]))
    story.append(Paragraph(
        time.strftime("Generated %Y-%m-%d %H:%M:%S", time.localtime()), accent))
    story.append(Spacer(1, 0.4 * cm))

    if summary:
        story.append(Paragraph("Summary", styles["Heading2"]))
        for k, v in summary.items():
            story.append(Paragraph(f"<b>{k}:</b> {v}", styles["Normal"]))
        story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph(f"Alerts ({len(alerts)})", styles["Heading2"]))

    header = ["Time", "Process", "PID", "Risk", "Severity", "Top reason"]
    data = [header]
    for a in alerts:
        top_reason = (a.reasons[0] if a.reasons else "")[:70]
        data.append([
            time.strftime("%m-%d %H:%M", time.localtime(a.timestamp)),
            a.process_name[:24], str(a.pid), f"{a.risk_score:.0f}",
            a.severity.label, top_reason,
        ])

    table = Table(data, repeatRows=1, colWidths=[2.2 * cm, 3.2 * cm, 1.4 * cm, 1.3 * cm, 2 * cm, 7 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1976D2")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F6FC")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(
        "Generated by ProcAI - defensive endpoint monitoring. This report was "
        "produced locally; no data left this machine.", accent))

    doc.build(story)
    audit.record("report.export", {"format": "pdf", "kind": "alerts", "count": len(alerts)})
    log.info("Exported PDF report to %s", path)
    return path
