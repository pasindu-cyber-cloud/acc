<#
.SYNOPSIS
    Build, test and publish ProcAI (.NET 8) for Windows.

.DESCRIPTION
    Restores, builds and runs the test suite, then publishes the WPF app and the
    background service as self-contained single-file executables for win-x64.
    Optionally compiles the Inno Setup installer if ISCC is on PATH.

.EXAMPLE
    pwsh ./build.ps1                # build + test + publish
    pwsh ./build.ps1 -Installer     # also compile the Inno Setup installer
#>
param(
    [switch]$Installer,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$publishDir = Join-Path $root "publish"

Write-Host "==> Restoring..." -ForegroundColor Cyan
dotnet restore (Join-Path $root "ProcAI.sln")

Write-Host "==> Building (Release)..." -ForegroundColor Cyan
dotnet build (Join-Path $root "ProcAI.sln") -c Release --no-restore

if (-not $SkipTests) {
    Write-Host "==> Testing..." -ForegroundColor Cyan
    dotnet test (Join-Path $root "ProcAI.sln") -c Release --no-build
}

$pubArgs = @(
    "-c", "Release", "-r", "win-x64", "--self-contained", "true",
    "/p:PublishSingleFile=true", "/p:IncludeNativeLibrariesForSelfExtract=true"
)

Write-Host "==> Publishing dashboard (ProcAI.exe)..." -ForegroundColor Cyan
dotnet publish (Join-Path $root "src/ProcAI.App/ProcAI.App.csproj") @pubArgs `
    -o (Join-Path $publishDir "app")

Write-Host "==> Publishing service (ProcAI.Service.exe)..." -ForegroundColor Cyan
dotnet publish (Join-Path $root "src/ProcAI.Service/ProcAI.Service.csproj") @pubArgs `
    -o (Join-Path $publishDir "service")

Write-Host "Published to $publishDir" -ForegroundColor Green

if ($Installer) {
    $iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($null -eq $iscc) {
        Write-Warning "Inno Setup (ISCC.exe) not found on PATH; skipping installer. See installer/INSTALLER.md."
    } else {
        Write-Host "==> Building installer..." -ForegroundColor Cyan
        & $iscc.Source (Join-Path $root "installer/procai_installer.iss")
    }
}
