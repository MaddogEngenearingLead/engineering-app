# Windows packaging helper
# Builds the GUI executable, then compiles the installer.

param(
    [switch]$SkipInstaller,
    [string]$InnoCompilerPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

Write-Host "Installing required dependencies..." -ForegroundColor Cyan
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller tkinterdnd2==0.4.2

if (-not $SkipInstaller) {
    powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "installer\build-installer.ps1") -InnoCompilerPath $InnoCompilerPath
} else {
    python build_exe.py
    Write-Host "Skipped installer build. Executable is at dist\JobManager.exe" -ForegroundColor Yellow
}
