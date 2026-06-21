# ProcAI for Windows (.NET 8 / C# / WPF)

A native Windows rebuild of ProcAI — a **defensive, transparent, user-consented**
endpoint-security tool — engineered for speed and a smooth, modern Fluent UI.

This is a feature-for-feature reimplementation of the Python prototype with
native performance, real-time process telemetry, and a Windows 11-style
interface.

## Why C# / .NET 8

| Concern | Implementation |
|---|---|
| Performance & responsiveness | Compiled, true multithreading, async I/O, low memory |
| Process telemetry | `System.Diagnostics`, **WMI** (`System.Management`), **ETW** (planned), IP Helper API (P/Invoke) for per-process network |
| Code-signing reputation | Native **Authenticode** verification (`WinVerifyTrust` / `X509Certificate`) |
| Machine learning | **ML.NET** — `FastForest` (Random Forest) and `FastTree` (decision trees) |
| Storage | **SQLite** via `Microsoft.Data.Sqlite` + Dapper |
| GUI | **WPF + WPF-UI** (Fluent / Mica), MVVM via `CommunityToolkit.Mvvm`, charts via LiveCharts |
| Background | **Windows Service** (`BackgroundService`) + tray icon (`H.NotifyIcon`) + toast notifications |
| Packaging | Single-file self-contained publish + WiX/Inno installer, Authenticode signing |

## Solution layout

```
dotnet/
  ProcAI.sln
  src/
    ProcAI.Core/      detection engine (models, telemetry, rules, baseline, ML, hybrid, data, audit)
    ProcAI.App/       WPF dashboard (Views + ViewModels + Services), tray, notifications
    ProcAI.Service/   headless Windows Service host for background monitoring
  tests/
    ProcAI.Tests/     xUnit unit + integration tests for the engine
  installer/          packaging + code-signing guidance
```

## Build & run (on Windows)

Requires the free **.NET 8 SDK** (https://dotnet.microsoft.com/download).

```powershell
cd dotnet
dotnet restore
dotnet build -c Release
dotnet run -c Release --project src\ProcAI.App      # launch the dashboard
dotnet run -c Release --project src\ProcAI.Service  # run the background service
dotnet test                                         # run the test suite
```

Publish a single-file executable:

```powershell
dotnet publish src\ProcAI.App -c Release -r win-x64 --self-contained true ^
  /p:PublishSingleFile=true /p:IncludeNativeLibrariesForSelfExtract=true
```

## Same defensive guarantees

Never hides, never disables Windows Defender, never auto-terminates (manual +
confirmation + audit), privacy-first by default, tamper-evident audit log, and an
honest Protection Health page that does not impersonate Microsoft Defender.

## Status

Built incrementally. See `docs/ARCHITECTURE.md` for the design and the porting
map from the Python prototype.
