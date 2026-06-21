"""ProcAI detection core.

The core package is intentionally decoupled from the GUI and from optional
heavy dependencies. The detection pipeline is:

    telemetry -> features -> (rules + baseline + ML) -> hybrid -> alert

``models`` holds the plain dataclasses passed between these stages.
"""
