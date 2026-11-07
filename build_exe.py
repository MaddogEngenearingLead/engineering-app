"""Build a standalone Job Manager app for the current OS: python build_exe.py (requires pyinstaller).

PyInstaller cannot cross-compile, so run this on Windows (-> dist/JobManager.exe)
or macOS (-> dist/JobManager.app) or use the "Build GUI" GitHub Actions workflow.

The BOM scan runs inside the app, so the PDF/BOM libraries are bundled too.
"""
import os
import sys
from pathlib import Path

import PyInstaller.__main__

args = [
    "run_gui.py",
    "--name", "JobManager",
    "--windowed",
    "--collect-all", "tkinterdnd2",
    "--collect-all", "pdfplumber",
    "--collect-all", "pdfminer",
    "--collect-all", "reportlab",
    "--collect-submodules", "app",
    "--collect-all", "certifi",
    "--collect-all", "pypdfium2",
    "--collect-all", "pypdfium2_raw",
    "--collect-all", "httpx",
    "--hidden-import", "docx",
    "--hidden-import", "openpyxl",
    "--noconfirm",
]
bundle_dir = os.environ.get("TESSERACT_BUNDLE_DIR")
if bundle_dir:
    root = Path(bundle_dir).expanduser().resolve()
    executable = root / ("tesseract.exe" if sys.platform.startswith("win") else "tesseract")
    if not all(path.is_file() for path in (executable, root / "tessdata" / "eng.traineddata",
                                           root / "tessdata" / "pdf.ttf")):
        raise SystemExit("TESSERACT_BUNDLE_DIR must contain tesseract, tessdata/eng.traineddata and tessdata/pdf.ttf.")
    args += ["--add-data", f"{root}{os.pathsep}tesseract"]
# --onefile with --windowed is deprecated on macOS, which builds a .app bundle instead
if sys.platform != "darwin":
    args.append("--onefile")

PyInstaller.__main__.run(args)
