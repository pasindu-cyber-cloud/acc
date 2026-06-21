"""Windows startup entry management (visible, user-consented).

When the user opts in, ProcAI adds a *visible* entry under the current user's
``HKCU\\...\\Run`` key so the background service starts at logon. This is the
standard, transparent Windows auto-start mechanism -- it appears in Task
Manager's Startup tab and can be removed by the user there or via this module.

ProcAI never installs hidden services, never writes to machine-wide keys without
elevation/consent, and always exposes a one-click way to disable startup.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ..utils import audit
from ..utils.logging_setup import get_logger

log = get_logger("service.autostart")

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "ProcAI"


def _command() -> str:
    """Best-effort command to launch the visible background service with a tray."""
    exe = Path(sys.executable)
    # When frozen by PyInstaller, sys.executable is the ProcAI exe itself.
    if getattr(sys, "frozen", False):
        return f'"{exe}" --service --tray'
    return f'"{exe}" -m procai.service.background --tray'


def is_enabled() -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _VALUE_NAME)
            return True
    except OSError:
        return False


def set_autostart(enable: bool) -> bool:
    """Enable/disable the logon startup entry. Returns the resulting state."""
    if not sys.platform.startswith("win"):
        raise RuntimeError("Startup entries are only supported on Windows.")
    import winreg

    if enable:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _command())
        audit.record("autostart.enable", {"command": _command()})
        log.info("Enabled ProcAI startup entry.")
        return True
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, _VALUE_NAME)
        audit.record("autostart.disable", {})
        log.info("Removed ProcAI startup entry.")
    except OSError:
        pass
    return False
