"""Build a standalone Job Manager app for the current OS: python build_exe.py (requires pyinstaller).

PyInstaller cannot cross-compile, so run this on Windows (-> dist/JobManager/JobManager.exe)
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
    name = "tesseract.exe" if sys.platform.startswith("win") else "tesseract"
    if not ((root / name).is_file() or (root / "bin" / name).is_file()) or not all(
        path.is_file() for path in (root / "tessdata" / "eng.traineddata", root / "tessdata" / "pdf.ttf")
    ):
        raise SystemExit("TESSERACT_BUNDLE_DIR must contain tesseract, tessdata/eng.traineddata and tessdata/pdf.ttf.")
    args += ["--add-data", f"{root}{os.pathsep}tesseract"]
# Keep the large Ollama runtime in the app folder so it is not extracted to a
# temporary directory on every Windows app launch.
ollama_dir = os.environ.get("OLLAMA_BUNDLE_DIR")
if ollama_dir:
    runtime = Path(ollama_dir).expanduser().resolve()
    if not runtime.is_dir():
        raise SystemExit("OLLAMA_BUNDLE_DIR must point to the verified Ollama runtime directory.")
    args += ["--add-data", f"{runtime}{os.pathsep}ollama-runtime"]
if sys.platform not in ("darwin", "win32"):
    args.append("--onefile")

PyInstaller.__main__.run(args)
