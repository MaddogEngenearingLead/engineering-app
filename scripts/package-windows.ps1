# Windows packaging helper

This script builds the GUI executable and then launches the installer build script.

param(
    [switch]$SkipInstaller,
    [string]$InnoCompilerPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)

$ErrorActionPreference = "Stop"

Write-Host "Installing/refreshing required packaging dependencies..." -ForegroundColor Cyan
python -m pip install --upgrade pip
python -m pip install pyinstaller tkinterdnd2==0.4.2

Write-Host "Building executable with PyInstaller..." -ForegroundColor Cyan
python build_exe.py

if (-not $SkipInstaller) {
    Write-Host "Building installer..." -ForegroundColor Cyan
    powershell -ExecutionPolicy Bypass -File .\installer\build-installer.ps1 -InnoCompilerPath $InnoCompilerPath
} else {
    Write-Host "Skipped installer build. Executable should be at dist\JobManager.exe" -ForegroundColor Yellow
}
