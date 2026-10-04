"""Build a standalone Job Manager app for the current OS: python build_exe.py (requires pyinstaller).

PyInstaller cannot cross-compile, so run this on Windows (-> dist/JobManager.exe)
or macOS (-> dist/JobManager.app) or use the "Build GUI" GitHub Actions workflow.
"""
import sys

import PyInstaller.__main__

args = [
    "run_gui.py",
    "--name", "JobManager",
    "--windowed",
    "--collect-all", "tkinterdnd2",
    "--noconfirm",
]
# --onefile with --windowed is deprecated on macOS, which builds a .app bundle instead
if sys.platform != "darwin":
    args.append("--onefile")

PyInstaller.__main__.run(args)
