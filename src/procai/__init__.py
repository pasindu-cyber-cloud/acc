"""ProcAI - defensive, transparent, AI-assisted suspicious-process detection.

ProcAI is endpoint-security software for Windows that monitors running processes,
builds a baseline of normal behaviour, and uses a transparent hybrid engine
(rule-based scoring + statistical deviation + machine learning) to flag
suspicious activity. It is strictly defensive: it never hides itself, never
disables Windows Defender, and never exfiltrates data without explicit consent.
"""

from __future__ import annotations

__all__ = ["__version__", "APP_NAME", "APP_VENDOR"]

__version__ = "2.0.0"
APP_NAME = "ProcAI"
APP_VENDOR = "ProcAI Project"
