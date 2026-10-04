<#
Builds the Windows executable and compiles an installer via Inno Setup.

Usage:
  powershell -ExecutionPolicy Bypass -File .\installer\build-installer.ps1

Optional:
  powershell -ExecutionPolicy Bypass -File .\installer\build-installer.ps1 -InnoCompilerPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
#>
param(
    [string]$InnoCompilerPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

Write-Host "[1/3] Building GUI executable..." -ForegroundColor Cyan
python build_exe.py

$exePath = Join-Path $repoRoot "dist\JobManager.exe"
if (-not (Test-Path $exePath)) {
    throw "Build failed: $exePath not found."
}

Write-Host "[2/3] Checking Inno Setup compiler..." -ForegroundColor Cyan
if (-not (Test-Path $InnoCompilerPath)) {
    throw "Inno Setup compiler not found at: $InnoCompilerPath"
}

$issPath = Join-Path $PSScriptRoot "EngineeringApp.iss"
if (-not (Test-Path $issPath)) {
    throw "Installer script not found at: $issPath"
}

Write-Host "[3/3] Compiling installer..." -ForegroundColor Cyan
& "$InnoCompilerPath" "$issPath"

Write-Host "Done. Installer output:" -ForegroundColor Green
Write-Host "  $PSScriptRoot\Output\EngineeringAppSetup.exe"
