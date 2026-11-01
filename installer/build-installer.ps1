<#
Builds the Windows executable and compiles an installer via Inno Setup.

Usage:
  powershell -ExecutionPolicy Bypass -File .\installer\build-installer.ps1

Optional (force a specific compiler):
  powershell -ExecutionPolicy Bypass -File .\installer\build-installer.ps1 -InnoCompilerPath "C:\path\to\ISCC.exe"
#>
param(
    [string]$InnoCompilerPath = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

function Find-Iscc {
    param([string]$Override)

    if ($Override) {
        if (Test-Path $Override) { return $Override }
        throw "Inno Setup compiler not found at the path you provided: $Override"
    }

    $candidates = @(
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) { return $c }
    }

    # Is it on PATH?
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    # Registry uninstall entries
    $regPaths = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    foreach ($rp in $regPaths) {
        $entry = Get-ItemProperty $rp -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -like "Inno Setup*" -and $_.InstallLocation } |
            Select-Object -First 1
        if ($entry) {
            $p = Join-Path $entry.InstallLocation "ISCC.exe"
            if (Test-Path $p) { return $p }
        }
    }

    # Recursive probe as a last resort
    $roots = @($env:ProgramFiles, ${env:ProgramFiles(x86)}, "$env:LOCALAPPDATA\Programs") |
        Where-Object { $_ -and (Test-Path $_) }
    foreach ($r in $roots) {
        $found = Get-ChildItem -Path $r -Recurse -Filter ISCC.exe -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($found) { return $found.FullName }
    }

    return $null
}

Write-Host "[1/3] Building GUI executable..." -ForegroundColor Cyan
python build_exe.py

$exePath = Join-Path $repoRoot "dist\JobManager.exe"
if (-not (Test-Path $exePath)) {
    throw "Build failed: $exePath not found."
}

Write-Host "[2/3] Locating Inno Setup compiler..." -ForegroundColor Cyan
$iscc = Find-Iscc -Override $InnoCompilerPath
if (-not $iscc) {
    throw "Inno Setup compiler (ISCC.exe) not found. Install it with: winget install --id JRSoftware.InnoSetup -e   (then rerun), or pass -InnoCompilerPath."
}
Write-Host "Using: $iscc" -ForegroundColor Green

$issPath = Join-Path $PSScriptRoot "EngineeringApp.iss"
if (-not (Test-Path $issPath)) {
    throw "Installer script not found at: $issPath"
}

Write-Host "[3/3] Compiling installer..." -ForegroundColor Cyan
& "$iscc" "$issPath"
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compile failed with exit code $LASTEXITCODE"
}

$out = Join-Path $PSScriptRoot "Output\EngineeringAppSetup.exe"
if (Test-Path $out) {
    Write-Host "Done. Installer created:" -ForegroundColor Green
    Write-Host "  $out"
} else {
    throw "Compile finished but installer not found at $out"
}
