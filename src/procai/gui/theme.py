"""Visual theme: colours, fonts, and severity styling for the GUI.

Centralising colours keeps the look consistent and makes it easy to retheme.
Colours are chosen for a modern dark "security console" aesthetic with clear,
accessible severity coding.
"""

from __future__ import annotations

from ..core.models import Severity

# Brand / surface palette
PRIMARY = "#2196F3"
PRIMARY_DARK = "#1565C0"
BG = "#0F1419"
SURFACE = "#1A222C"
SURFACE_2 = "#222C38"
SIDEBAR = "#141B24"
TEXT = "#E6EDF3"
TEXT_MUTED = "#8B98A5"
BORDER = "#2A3845"
SUCCESS = "#2ECC71"
WARNING = "#F39C12"

# Severity -> (colour, label)
SEVERITY_COLORS: dict[Severity, str] = {
    Severity.INFO: "#5DADE2",
    Severity.LOW: "#58D68D",
    Severity.MEDIUM: "#F4D03F",
    Severity.HIGH: "#E67E22",
    Severity.CRITICAL: "#E74C3C",
}


def severity_color(sev: Severity) -> str:
    return SEVERITY_COLORS.get(sev, TEXT_MUTED)


def risk_color(score: float) -> str:
    return severity_color(Severity.from_score(score))


# Font families/sizes (CustomTkinter accepts (family, size, style) tuples).
FONT_FAMILY = "Segoe UI"
FONT_TITLE = (FONT_FAMILY, 22, "bold")
FONT_HEADING = (FONT_FAMILY, 16, "bold")
FONT_SUBHEADING = (FONT_FAMILY, 13, "bold")
FONT_BODY = (FONT_FAMILY, 12)
FONT_SMALL = (FONT_FAMILY, 11)
FONT_MONO = ("Consolas", 11)

# Sidebar navigation definition: (page_key, label, icon-glyph)
NAV_ITEMS: list[tuple[str, str, str]] = [
    ("overview", "Overview", "\u2302"),            # house
    ("live", "Live Processes", "\u2261"),          # list
    ("alerts", "Alerts", "\u26A0"),                # warning
    ("intelligence", "Process Intelligence", "\u25C9"),
    ("deep_scan", "Deep Scan", "\u2315"),          # magnifier
    ("timeline", "Forensic Timeline", "\u29D6"),
    ("assistant", "Proc Assistant", "\u2728"),     # sparkles
    ("reports", "Reports", "\u2398"),
    ("settings", "Settings", "\u2699"),            # gear
    ("health", "Protection Health", "\u2764"),     # heart
]
