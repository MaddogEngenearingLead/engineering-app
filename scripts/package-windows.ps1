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
    $ollamaBundle = Join-Path $repoRoot "build\ollama-bundle"
    python scripts/prepare_ollama_bundle.py --output $ollamaBundle
    if ($LASTEXITCODE -ne 0) {
        throw "Ollama runtime preparation failed with exit code $LASTEXITCODE"
    }
    $env:OLLAMA_BUNDLE_DIR = Join-Path $ollamaBundle "ollama-runtime"
    python build_exe.py
    Write-Host "Skipped installer build. Application is at dist\JobManager" -ForegroundColor Yellow
}
