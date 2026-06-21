# ProcAI Packaging, Installer & Deployment Guide

ProcAI ships as a standard, transparent Windows application. This document
covers building the executable, producing an installer, and distributing it
legitimately. **ProcAI never bypasses SmartScreen, Windows Defender, UAC, or any
other Windows security control.** Trust is established the correct way: through
code signing and reputation, not evasion.

## 1. Prerequisites

- Windows 10/11 (x64)
- Python 3.10–3.12
- `pip install -r requirements-dev.txt` (includes PyInstaller and all extras)
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) for the `.exe` installer (optional)

## 2. Build the executable

```bat
python installer\build.py
```

This invokes PyInstaller with `installer/procai.spec` and produces
`dist\ProcAI\ProcAI.exe` plus its dependencies. The same executable runs:

- the GUI dashboard: `ProcAI.exe`
- the background service: `ProcAI.exe --service --tray`
- a cooperative stop signal: `ProcAI.exe --stop`

UPX compression is intentionally disabled in the spec because compressed
executables frequently trigger antivirus heuristics — we prefer clean,
inspectable binaries.

## 3. Build the installer

```bat
python installer\build.py --installer
```

The Inno Setup script (`installer/procai_installer.iss`) creates:

- Start Menu shortcuts (Dashboard, background service, Uninstall)
- an optional Desktop shortcut
- an **optional, clearly-labelled** "start at logon" entry — a *visible* `HKCU\…\Run`
  value that appears in Task Manager → Startup and is removed on uninstall
- a standard uninstaller that stops the service, removes files and the startup
  entry, and **asks** whether to also delete local data (reports, logs, database)

Installs per-user by default (no admin prompt); the user may choose all-users.

## 4. Application & data layout after install

| Location | Contents |
|---|---|
| `%PROGRAMFILES%\ProcAI` or per-user app dir | program files, `ProcAI.exe` |
| `%LOCALAPPDATA%\ProcAI` | `procai.db`, `settings.json`, `models\`, `reports\`, `logs\` |
| `%LOCALAPPDATA%\ProcAI\logs\audit.log` | tamper-evident audit log |

## 5. Code signing (recommended, legitimate trust)

Signing reduces SmartScreen friction **honestly** — it does not hide anything.

1. Obtain an Authenticode code-signing certificate (OV, or EV for instant
   SmartScreen reputation) from a trusted CA.
2. Sign the executable and the installer with the official `signtool`:

   ```bat
   signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 ^
       /a dist\ProcAI\ProcAI.exe
   signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 ^
       /a installer\Output\ProcAI-Setup-2.0.0.exe
   ```

3. Submit the signed installer to Microsoft for malware analysis if desired to
   build reputation faster. **Do not** attempt to forge Microsoft signatures or
   spoof publisher identity — that is both illegal and detectable.

## 6. Windows Security Center integration — honest position

Registering as an official **antivirus provider** in the Windows Security Center
requires participation in the Microsoft Virus Initiative (MVI), a signed
WSC-compatible product, and a kernel/ELAM footprint that is out of scope for a
Python prototype. ProcAI therefore **does not** claim AV-provider status.

Instead, ProcAI provides an in-app **Protection Health** page that transparently
reports its own state (monitoring, model, baseline, notifications, tray, audit
integrity). It clearly states it is independent software and that the user
should keep Windows Defender enabled. This is the safe, honest equivalent for a
prototype and is exactly what should be demonstrated for a dissertation.

## 7. Uninstall

Use *Apps & features* or the Start Menu *Uninstall ProcAI* shortcut. The
uninstaller stops the service, removes the startup entry and program files, and
prompts whether to keep or delete your local data.
