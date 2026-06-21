"""Process reputation indicators (advisory, defensive, read-only).

This module enriches a :class:`ProcessSnapshot` with reputation context:

* **Code-signing status** -- whether the executable is Authenticode-signed and,
  if so, the signer name (Windows only, via PowerShell ``Get-AuthenticodeSignature``).
  Results are cached per executable path to avoid repeated shell calls.
* **Suspicious directory** -- whether the executable lives in a commonly-abused
  location (Temp, Downloads, Public, recycle bin...).
* **Startup persistence** -- whether the executable is referenced by a Windows
  auto-start location (Run keys, Startup folders). Visibility only; ProcAI never
  creates or removes persistence on the user's behalf.

Important: "unsigned" or "runs from Temp" are *signals*, never proof of malice.
They contribute weighted points to the transparent rule engine and are always
shown to the user with their reasoning.
"""

from __future__ import annotations

import functools
import os
import subprocess
import sys
from typing import Optional

from .models import ProcessSnapshot
from ..config import SUSPICIOUS_DIR_HINTS
from ..utils.logging_setup import get_logger

log = get_logger("core.reputation")

_IS_WINDOWS = sys.platform.startswith("win")


# --------------------------------------------------------------------------- #
# Suspicious directory
# --------------------------------------------------------------------------- #
def is_suspicious_path(exe_path: str) -> bool:
    if not exe_path:
        return False
    p = exe_path.replace("/", "\\").lower() if _IS_WINDOWS else exe_path.lower()
    norm = exe_path.lower()
    return any(hint in p or hint in norm for hint in SUSPICIOUS_DIR_HINTS)


# --------------------------------------------------------------------------- #
# Code signing (Windows)
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=2048)
def signature_status(exe_path: str) -> tuple[Optional[bool], str]:
    """Return ``(is_signed, signer)``.

    ``is_signed`` is ``None`` when signing status cannot be determined (e.g. not
    on Windows, file missing, or PowerShell unavailable). The result is cached.
    """
    if not exe_path or not os.path.exists(exe_path):
        return None, ""
    if not _IS_WINDOWS:
        # Signature verification is a Windows Authenticode concept; on other
        # platforms we simply report "unknown" rather than guessing.
        return None, ""
    try:
        # PowerShell is present on all supported Windows versions. We only READ
        # the signature; nothing is modified.
        ps = (
            "$ErrorActionPreference='SilentlyContinue';"
            f"$s=Get-AuthenticodeSignature -LiteralPath '{exe_path}';"
            "Write-Output $s.Status;"
            "Write-Output $s.SignerCertificate.Subject"
        )
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=8,
        )
        lines = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
        if not lines:
            return None, ""
        status = lines[0].lower()
        signer = ""
        if len(lines) > 1:
            # Subject looks like "CN=Example Corp, O=..., C=..."; extract CN.
            for part in lines[1].split(","):
                if part.strip().upper().startswith("CN="):
                    signer = part.strip()[3:]
                    break
            signer = signer or lines[1]
        is_signed = status == "valid"
        return is_signed, signer
    except (subprocess.SubprocessError, OSError) as exc:  # pragma: no cover
        log.debug("Signature check failed for %s: %s", exe_path, exc)
        return None, ""


# --------------------------------------------------------------------------- #
# Startup persistence visibility (Windows)
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=1)
def _startup_references() -> frozenset[str]:
    """Collect executable paths referenced by common auto-start locations.

    Read-only. Returns lowercased path fragments found in Run registry keys and
    user/common Startup folders.
    """
    refs: set[str] = set()
    if not _IS_WINDOWS:
        return frozenset(refs)

    # Run keys (current user + local machine), read-only.
    try:
        import winreg  # type: ignore

        run_keys = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        ]
        for hive, subkey in run_keys:
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    i = 0
                    while True:
                        try:
                            _, value, _ = winreg.EnumValue(key, i)
                            refs.add(str(value).lower())
                            i += 1
                        except OSError:
                            break
            except OSError:
                continue
    except Exception:  # pragma: no cover
        pass

    # Startup folders.
    for env in ("APPDATA", "PROGRAMDATA"):
        base = os.environ.get(env)
        if not base:
            continue
        startup = os.path.join(base, r"Microsoft\Windows\Start Menu\Programs\Startup")
        try:
            for entry in os.scandir(startup):
                refs.add(entry.path.lower())
                refs.add(entry.name.lower())
        except OSError:
            continue
    return frozenset(refs)


def is_startup_persistent(snap: ProcessSnapshot) -> bool:
    refs = _startup_references()
    if not refs:
        return False
    exe = (snap.exe_path or "").lower()
    name = (snap.name or "").lower()
    for ref in refs:
        if exe and exe in ref:
            return True
        if name and name in ref:
            return True
    return False


# --------------------------------------------------------------------------- #
# Enrichment entry point
# --------------------------------------------------------------------------- #
def enrich(snap: ProcessSnapshot, *, check_signature: bool = True) -> ProcessSnapshot:
    """Populate reputation fields on a snapshot in place and return it."""
    snap.in_suspicious_dir = is_suspicious_path(snap.exe_path)
    snap.is_startup_persistent = is_startup_persistent(snap)
    if check_signature and snap.exe_path:
        signed, signer = signature_status(snap.exe_path)
        snap.is_signed = signed
        snap.signer = signer
    return snap


def clear_caches() -> None:
    """Clear reputation caches (call after the user rescans / changes settings)."""
    signature_status.cache_clear()
    _startup_references.cache_clear()
