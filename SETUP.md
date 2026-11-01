# Setup

## End users
Download `JobManager.exe` (Windows) or `JobManager-macos.zip` (macOS) from the latest
release and run it. No Python needed. See [`README.md`](README.md) for how to use it.

## Developers

Prerequisites: Python 3.12, git, and on Linux `python3-tk` (plus `xvfb` for headless GUI checks).

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
| Build the app for this OS | `pip install pyinstaller && python build_exe.py` |
| Run the optional HTTP API | `uvicorn app.main:app --reload` → <http://localhost:8000/docs> |

Each job keeps its files and a `bom_exports/` folder (`review.json`, PDF, CSV, JSON).

## Releasing
1. Open a PR from a feature branch and merge it into `master`.
2. Tag the merge: `git tag vX.Y.Z && git push origin vX.Y.Z`.
3. GitHub Actions (`Build GUI`) stamps the version, builds and self-tests both apps, and publishes
   `JobManager.exe` and `JobManager-macos.zip` to the release. Installed apps offer the update.

The workflow needs a repository secret `UPDATE_TOKEN` (read-only, Contents: read) so installed
apps of a private repository can check for updates.

## Optional HTTP API
Environment overrides (`.env`): `APP_NAME`, `ENVIRONMENT`, `UPLOAD_DIR` (default `backend/uploads`),
`MAX_UPLOAD_SIZE_MB` (25), `CORS_ORIGINS`. Docker: `docker build -t engineering-app .` then
`docker run --rm -p 8000:8000 engineering-app`.

## Troubleshooting
- **`ModuleNotFoundError`** – activate the virtual environment and re-run `pip install -r requirements.txt`.
- **Tk errors on Linux** – install `python3-tk`.
- **"Failed to load Python DLL" after an update** – fixed in v0.1.5; if you are on an older
  version, download the latest `JobManager.exe` once by hand.
