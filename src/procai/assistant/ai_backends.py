"""Optional AI chat backends for the Proc Assistant (privacy-gated).

Two optional backends are supported for richer, conversational investigation:

* **Ollama** -- a *local* LLM server (default ``http://localhost:11434``). This
  keeps data on the machine and is the recommended privacy-preserving option.
* **Gemini** -- Google's hosted API. This sends prompt text off the device and
  is therefore only allowed when the user has explicitly disabled privacy-first
  mode and enabled the assistant.

Hard privacy rules enforced here:

* If ``settings.ai_assistant_enabled`` is False -> backends are unavailable.
* If ``settings.privacy_first_mode`` is True -> only the *local* Ollama backend
  is permitted; the cloud Gemini backend is refused.
* The offline rule-based explainer is always the default and never sends data.

``requests`` is imported lazily; absence simply disables the network backends.
"""

from __future__ import annotations

from typing import Optional

from ..config import Settings
from ..utils import audit
from ..utils.logging_setup import get_logger

log = get_logger("assistant.ai")

try:  # pragma: no cover - only where the ai extra is installed
    import requests

    _HAVE_REQUESTS = True
except Exception:  # pragma: no cover
    _HAVE_REQUESTS = False


class AIUnavailable(RuntimeError):
    """Raised when an AI backend cannot be used (disabled, privacy, missing dep)."""


def backend_status(settings: Settings) -> dict[str, object]:
    """Describe what the assistant can currently do, for the GUI."""
    return {
        "offline_always_available": True,
        "assistant_enabled": settings.ai_assistant_enabled,
        "privacy_first": settings.privacy_first_mode,
        "requests_installed": _HAVE_REQUESTS,
        "selected_backend": settings.ai_backend,
        "cloud_allowed": settings.ai_assistant_enabled and not settings.privacy_first_mode,
    }


def _guard(settings: Settings, *, requires_network: bool, cloud: bool) -> None:
    if not settings.ai_assistant_enabled:
        raise AIUnavailable("AI assistant is disabled. Enable it in Settings to use chat mode.")
    if requires_network and not _HAVE_REQUESTS:
        raise AIUnavailable("The 'requests' package is not installed (pip install procai[ai]).")
    if cloud and settings.privacy_first_mode:
        raise AIUnavailable(
            "Privacy-first mode blocks cloud AI. Use the local Ollama backend or "
            "disable privacy-first mode explicitly."
        )


def ask(settings: Settings, prompt: str, *, context: str = "") -> str:
    """Route a question to the configured AI backend.

    The caller is expected to have already built a rich, *local* context string
    (e.g. from :func:`procai.assistant.explain.explain_detection`). Only the
    chosen backend decides whether that text stays local (Ollama) or is sent to
    a cloud API (Gemini, non-privacy mode only).
    """
    backend = settings.ai_backend
    full_prompt = _compose_prompt(prompt, context)

    if backend == "ollama":
        _guard(settings, requires_network=True, cloud=False)
        audit.record("assistant.query", {"backend": "ollama", "local": True})
        return _ask_ollama(settings, full_prompt)
    if backend == "gemini":
        _guard(settings, requires_network=True, cloud=True)
        audit.record("assistant.query", {"backend": "gemini", "local": False})
        return _ask_gemini(settings, full_prompt)
    raise AIUnavailable(
        "No cloud/local AI backend selected. The offline explainer is being used instead."
    )


_SYSTEM_PREAMBLE = (
    "You are Proc Assistant, a careful, defensive cybersecurity helper inside the "
    "ProcAI endpoint-security tool. Explain process behaviour in clear, plain "
    "language. Be cautious and never tell the user to disable security software. "
    "Recommend safe, reversible investigation steps. If evidence is weak, say so."
)


def _compose_prompt(question: str, context: str) -> str:
    parts = [_SYSTEM_PREAMBLE]
    if context:
        parts.append("\n--- Detection context (from ProcAI, on this machine) ---\n" + context)
    parts.append("\n--- User question ---\n" + question)
    return "\n".join(parts)


def _ask_ollama(settings: Settings, prompt: str) -> str:
    url = settings.ai_ollama_host.rstrip("/") + "/api/generate"
    try:
        resp = requests.post(
            url,
            json={"model": settings.ai_ollama_model, "prompt": prompt, "stream": False},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip() or "(empty response)"
    except Exception as exc:
        raise AIUnavailable(f"Could not reach local Ollama at {settings.ai_ollama_host}: {exc}")


def _ask_gemini(settings: Settings, prompt: str) -> str:
    if not settings.ai_gemini_api_key:
        raise AIUnavailable("No Gemini API key set in Settings.")
    model = "gemini-1.5-flash"
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        f"?key={settings.ai_gemini_api_key}"
    )
    try:
        resp = requests.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return (
            data["candidates"][0]["content"]["parts"][0]["text"].strip()
            or "(empty response)"
        )
    except Exception as exc:
        raise AIUnavailable(f"Gemini request failed: {exc}")
