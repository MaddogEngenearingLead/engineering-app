# Windows Installer (Inno Setup)

This project includes a Windows installer script that:

- Installs the packaged GUI application
- Creates a desktop shortcut
- Optionally launches the app after installation

## Prerequisites

1. Python 3.12
2. Project dependencies installed:
   ```powershell
   pip install -r requirements.txt
   pip install pyinstaller tkinterdnd2==0.4.2
   ```
3. Inno Setup 6 installed

## Build the app executable

From the repository root:

```powershell
python scripts/prepare_ollama_bundle.py --output build/ollama-bundle
$env:OLLAMA_BUNDLE_DIR = (Resolve-Path build/ollama-bundle/ollama-runtime).Path
python build_exe.py
```

This creates:

- `dist/JobManager/JobManager.exe` and its supporting runtime files

The helper downloads the pinned Ollama release, verifies its published SHA-256,
and extracts it for the folder-based app build.

## Build the installer

1. Open `installer/EngineeringApp.iss` in Inno Setup Compiler
2. Build (Compile)

Output installer is generated in `installer\Output\` as:

- `EngineeringAppSetup.exe`

## What the installer does

- Installs to `C:\Program Files\Engineering App` (default)
- Installs the complete `dist/JobManager` application folder, including its bundled Ollama runtime
- Creates Start Menu shortcut
- Creates desktop shortcut (default task)
- Adds "Launch Engineering App" checkbox on completion

## Silent install (optional)

```powershell
EngineeringAppSetup.exe /VERYSILENT /NORESTART
```

## Notes

- If your icon file changes, update `SetupIconFile` and shortcut icon references in `installer/EngineeringApp.iss`.
- Keep executable name aligned with `build_exe.py` (`JobManager.exe`).
