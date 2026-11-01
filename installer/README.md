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
python build_exe.py
```

This creates:

- `dist/JobManager.exe`

## Build the installer

1. Open `installer/EngineeringApp.iss` in Inno Setup Compiler
2. Build (Compile)

Output installer is generated in `installer\Output\` as:

- `EngineeringAppSetup.exe`

## What the installer does

- Installs to `C:\Program Files\Engineering App` (default)
- Copies `JobManager.exe` and required files
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
