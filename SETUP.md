# Setup

## End users
Download `JobManager-windows.zip` (Windows) or `JobManager-macos.zip` (macOS) from the latest
release. On Windows, extract the full folder before running `JobManager.exe`; on macOS, unzip
and open `JobManager.app`. No Python needed. See [`README.md`](README.md) for how to use it.
Windows users updating from v0.1.27 or earlier must download and extract the ZIP manually;
the older updater expects a single executable.

## Developers

Prerequisites: Python 3.12, git, and on Linux `python3-tk` (plus `xvfb` for headless GUI checks).
The updated release workflow bundles Tesseract and English language data for
image-only BOM/revision OCR on Windows and macOS. Previously published releases
and source installations require a separate Tesseract installation with English
data on `PATH`. Missing OCR or unreadable image-only sheets are flagged for review.

To build with a supplied, redistributable Tesseract installation, set
`TESSERACT_BUNDLE_DIR` before running `python build_exe.py`. The directory must
contain `tesseract.exe` (Windows) or `tesseract` (macOS/Linux), its required
runtime libraries, `tessdata/eng.traineddata`, and `tessdata/pdf.ttf`. The build
includes that directory and prefers it over
`PATH`; packaged `--selftest` exercises bundled OCR. Use an installation built for the target OS and
architecture, check its redistribution licenses, and test the resulting app on a
clean target machine: native library dependencies must also be portable. The release
workflow provisions Tesseract from conda-forge, includes package license notices,
and requires bundled OCR to pass its packaged self-test before publication.

```bash
git clone https://github.com/MaddogSTD/engineering-app.git
cd engineering-app
python -m venv .venv
source .venv/bin/activate         # Windows Git Bash: source .venv/Scripts/activate
                                  # Windows cmd/PowerShell: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

| Task | Command |
| --- | --- |
| Run the desktop app | `python run_gui.py` |
| Run the tests | `python -m pytest tests -q` |
| Headless self-test | `python run_gui.py --selftest` (Linux: `xvfb-run -a python run_gui.py --selftest`) |
| Build the app for this OS | Prepare the verified Ollama runtime with `python scripts/prepare_ollama_bundle.py --output build/ollama-bundle`, set `OLLAMA_BUNDLE_DIR` to `build/ollama-bundle/ollama-runtime`, then run `python build_exe.py` |
| Run the optional HTTP API | `uvicorn app.main:app --reload` → <http://localhost:8000/docs> |

Each job keeps its files and a `bom_exports/` folder (`review.json`, PDF, CSV, JSON).

## Releasing
1. Open a PR from a feature branch and merge it into `master`.
2. Tag the merge: `git tag vX.Y.Z && git push origin vX.Y.Z`.
3. GitHub Actions (`Build GUI`) stamps the version, builds and self-tests both apps, and publishes
   `JobManager-windows.zip` and `JobManager-macos.zip` to the release. Installed apps offer the update.

The workflow needs a repository secret `UPDATE_TOKEN` (read-only, Contents: read) so installed
apps of a private repository can check for updates.

## Optional HTTP API
Environment overrides (`.env`): `APP_NAME`, `ENVIRONMENT`, `UPLOAD_DIR` (default `backend/uploads`),
`MAX_UPLOAD_SIZE_MB` (25), `CORS_ORIGINS`. Docker: `docker build -t engineering-app .` then
`docker run --rm -p 8000:8000 engineering-app`.

## Troubleshooting
- **`ModuleNotFoundError`** – activate the virtual environment and re-run `pip install -r requirements.txt`.
- **Tk errors on Linux** – install `python3-tk`.
- **Local AI returns no answer** – the app retries empty chat responses and then tries
  Ollama's generate endpoint; this can take extra time and does not guarantee success.
  If the scan still fails, use **Open debug reports** and review the report before sharing
  it. New reports are in the `error` folder beside the jobs folder.
- **"Failed to load Python DLL" after an update** – fixed in v0.1.5; if you are on an older
  version, download and extract the latest `JobManager-windows.zip` once by hand.
