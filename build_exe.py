"""Build a standalone Job Manager executable: python build_exe.py (requires pyinstaller)."""
import PyInstaller.__main__

PyInstaller.__main__.run([
    "run_gui.py",
    "--name", "JobManager",
    "--onefile",
    "--windowed",
    "--collect-all", "tkinterdnd2",
    "--noconfirm",
])
