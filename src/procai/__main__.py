"""ProcAI entry point.

Usage:
    python -m procai                # launch the GUI dashboard
    python -m procai --service      # run the headless background service
    python -m procai --service --tray
    python -m procai --version

The ``procai`` console script (defined in pyproject) calls :func:`main`.
"""

from __future__ import annotations

import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--version" in argv or "-V" in argv:
        print(f"ProcAI {__version__}")
        return 0

    if "--stop" in argv:
        # Used by the uninstaller / scripts to politely stop a running service.
        # We never force-kill unrelated processes; this signals our own service
        # via a stop flag file that the background loop checks.
        from .service.background import request_stop

        request_stop()
        return 0

    if "--service" in argv:
        from .service.background import run_service_cli

        # Pass through remaining flags (e.g. --tray, --verbose).
        rest = [a for a in argv if a != "--service"]
        return run_service_cli(rest)

    # Default: GUI dashboard.
    from .gui.app import run

    return run()


if __name__ == "__main__":
    sys.exit(main())
