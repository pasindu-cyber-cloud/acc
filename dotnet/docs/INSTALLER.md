# ProcAI (.NET) Packaging, Installer & Service

ProcAI ships as a standard, transparent Windows application. **It never bypasses
SmartScreen, Windows Defender, UAC or any Windows security control.** Trust is
established the correct way — through code signing — not evasion.

## 1. Publish

```powershell
cd dotnet
pwsh .\build.ps1
```
Produces self-contained single-file executables in `publish\`:
- `publish\app\ProcAI.exe` — the dashboard
- `publish\service\ProcAI.Service.exe` — the background monitor

Self-contained means the target machine does **not** need the .NET runtime.

## 2. Build the installer

```powershell
pwsh .\build.ps1 -Installer        # or: ISCC.exe installer\procai_installer.iss
```
The Inno Setup script creates:
- Start Menu shortcuts + an optional Desktop shortcut
- an **optional, clearly-labelled** "start at logon" entry — a *visible* `HKCU\…\Run`
  value (appears in Task Manager → Startup), removed on uninstall
- an uninstaller that **asks** whether to also delete local data

Installs per-user by default (no admin prompt).

## 3. Optional: run as a Windows Service

The background monitor can run as a real Windows Service (transparent, visible,
stoppable). From an elevated PowerShell:

```powershell
New-Service -Name "ProcAIProtection" -BinaryPathName '"C:\Program Files\ProcAI\ProcAI.Service.exe"' `
            -DisplayName "ProcAI Protection" -StartupType Automatic
Start-Service ProcAIProtection
```
Stop/remove at any time:
```powershell
Stop-Service ProcAIProtection
sc.exe delete ProcAIProtection
```
The service is visible in `services.msc` and Task Manager. ProcAI never installs
hidden services and never conceals itself.

## 4. Data layout

| Location | Contents |
|---|---|
| `%PROGRAMFILES%\ProcAI` (or per-user) | `ProcAI.exe`, `ProcAI.Service.exe` |
| `%LOCALAPPDATA%\ProcAI` | `procai.db`, `settings.json`, `models\`, `reports\`, `logs\` |
| `%LOCALAPPDATA%\ProcAI\logs\audit.log` | tamper-evident audit log |

## 5. Code signing (recommended)

Signing reduces SmartScreen friction honestly:
```powershell
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a publish\app\ProcAI.exe
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a installer\Output\ProcAI-Setup-2.0.0.exe
```
Use an Authenticode certificate from a trusted CA (EV for instant reputation).
**Never** forge Microsoft signatures or spoof publisher identity.

## 6. Windows Security Center — honest position

Registering as an official antivirus provider requires the Microsoft Virus
Initiative, a WSC-compatible signed product and an ELAM/kernel footprint — out of
scope for this prototype. ProcAI therefore **does not** claim AV-provider status;
instead the in-app **Protection Health** page transparently reports its own state
and reminds the user to keep Windows Defender enabled.
