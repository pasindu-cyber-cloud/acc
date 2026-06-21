"""Proc Assistant: the explainable-AI layer.

Converts technical detection output into plain-language explanations,
recommendations and guided investigation. Works fully offline by default; an
optional AI chat mode (Gemini REST or local Ollama) can be enabled explicitly by
the user, honouring privacy-first mode.
"""

from .explain import explain_detection, investigation_guide, summarise_alert

__all__ = ["explain_detection", "investigation_guide", "summarise_alert"]
