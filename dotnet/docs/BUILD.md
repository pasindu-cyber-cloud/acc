# Building ProcAI (.NET)

## Prerequisites
- Windows 10/11 (x64)
- [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0) (free)
- Optional: Visual Studio 2022 (17.8+) or VS Code with the C# Dev Kit
- Optional (installer): [Inno Setup 6](https://jrsoftware.org/isinfo.php)

## Quick start

```powershell
cd dotnet
dotnet restore
dotnet build -c Release
dotnet run -c Release --project src\ProcAI.App      # launch the dashboard
```

First launch shows a consent screen; accept it and the dashboard opens. Open
**Live Processes → Simulate** to see detection working immediately.

## Run the background service (console mode for debugging)

```powershell
dotnet run -c Release --project src\ProcAI.Service
```

## Tests

```powershell
dotnet test
```

Covers feature extraction, baseline (Welford) statistics, the rule engine, the
hybrid fusion, simulation, the audit-log hash chain and the SQLite layer.

## Publish single-file executables

```powershell
pwsh .\build.ps1            # restore + build + test + publish to .\publish\
pwsh .\build.ps1 -Installer # also compile the Inno Setup installer (needs ISCC)
```

This produces self-contained `publish\app\ProcAI.exe` and
`publish\service\ProcAI.Service.exe` (no .NET runtime required on the target).

## NuGet dependencies

- **ProcAI.Core**: Microsoft.ML + Microsoft.ML.FastTree, Microsoft.Data.Sqlite,
  Dapper, System.Management, QuestPDF.
- **ProcAI.App**: WPF-UI (Fluent), CommunityToolkit.Mvvm.
- **ProcAI.Service**: Microsoft.Extensions.Hosting(.WindowsServices).
- **ProcAI.Tests**: xUnit, FluentAssertions.

## Notes
- The app targets `net8.0-windows` (WPF + Win32 APIs are Windows-only).
- The detection logic in `ProcAI.Core.Detection` is plain C# and is unit-tested
  without any Windows APIs.
