# Engineering App – P&ID vs Scope-of-Work BOM

A **local-only desktop app** that reads a P&ID drawing (PDF), compares it with a
scope-of-work document, and produces a bill of materials (BOM) containing only
what the scope calls for. Nothing leaves the computer: there are no accounts, no
login and no cloud service. The app only contacts GitHub to check for updates.

## How it works

1. **Create a job** – enter a job number and drop in the P&ID PDF and the scope (Word, PDF or text).
2. **Generate the BOM** – the app:
   - detects demo, new-work and legend pages and the markup colour convention
     (green = new, red = demo, blue clouds = future, bold = in scope, grey = existing);
   - counts tagged items on the new-work pages and records a drawing location
     (page and grid, e.g. `p4 D-12`) for each;
   - keeps an item only if it is new work **and** the scope refers to it (by tag, code or name);
   - adds scope-only rows for work the scope lists but the drawing cannot count
     (valves, flanges, supports), anchored to a page or nearby equipment;
   - lists highlighted piping runs by size.
3. **Review / clarify** – open the review window to:
   - see every item with its location and why it is on the BOM;
   - use **Show on drawing** with Previous/Next and zoom to look at each location;
   - answer the **questions** the scan could not settle (marked `[OPEN]` / `[answered]`).
     Each question says what is asked, why, and where on the drawing. Answers add or
     change BOM items and are recorded on the BOM; answered questions stop being flagged.
     Answers are kept if the BOM is regenerated;
   - edit, remove or add items and add free-text clarification notes.
4. **Save and re-export** – the BOM PDF (items, locations, clarifications, remaining
   review notes) is rewritten. CSV and JSON copies are written next to it in `bom_exports/`
   for internal use.

Nothing is specific to one drawing or scope; the files used during development are
test data only.

## Install (end users)

Download the latest release from the repository's **Releases** page:

- **Windows:** `JobManager.exe` (single file, no Python needed).
- **macOS:** `JobManager-macos.zip` (unzip and open `JobManager.app`).

**Portable use (USB drive, Windows):** run `JobManager.exe` from the drive and jobs are saved in a
`Jobs` folder next to it, so they travel with the program. On a normal hard drive, create an empty
`Jobs` folder beside the exe to get the same behaviour; otherwise jobs live in
`%LOCALAPPDATA%\EngineeringApp\uploads`. Existing jobs are not moved automatically; copy that
folder's contents into `Jobs` if you want them on the drive.

Updates: the app checks for a new version at launch and can update itself
(**Check for updates**). Releases are built automatically by GitHub Actions
(`.github/workflows/build-gui.yml`) when a `v*` tag is pushed. An optional Windows
installer is described in [`installer/README.md`](installer/README.md).

## Run from source (developers)

Requires Python 3.12 (3.10+ should work) and, on Linux, `python3-tk`.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python run_gui.py                # or: python -m app.gui
python -m pytest tests -q        # run the tests
python run_gui.py --selftest     # headless scan + review-save check (used by CI)
```

Build the standalone app on the target OS: `pip install pyinstaller && python build_exe.py`
(`dist/JobManager.exe` on Windows, `dist/JobManager.app` on macOS).

## Repository layout

```text
app/
  gui/job_manager_gui.py   # dashboard: jobs, file drop, scan progress, update banner
  gui/review_window.py     # review window, question dialog, drawing viewer
  job_manager.py           # job folders and job files (<uploads>/<job>.json)
  file_detector.py         # reads scope text (docx/pdf/txt)
  services/
    job_scan.py            # scan orchestration, review.json (edits + answers)
    scope_bom.py           # page classification, legend, scope items, pipeline
    pid_labels.py          # label scan, highlight regions, colour convention
    pid_markup.py          # pipe runs and markup notes
    pid_scope.py           # scope item extraction
    bom_select.py          # which items go on the BOM, and why
    review_questions.py    # flags -> questions; applying/undoing answers
    bom_export.py          # PDF / JSON / CSV export
    updater.py             # GitHub release check and in-place update
  version.py, update_config.py
  main.py, api/, config.py # optional local HTTP API (see below)
frontend/                  # legacy browser UI for the HTTP API (not used by the desktop app)
tests/                     # pytest suite
build_exe.py, run_gui.py   # packaging and entry point
installer/, scripts/       # optional Windows installer
```

## Optional local HTTP API

A small FastAPI service exposes the same scan for scripting:

```bash
uvicorn app.main:app --reload     # http://localhost:8000/docs
```

Main routes (prefix `/api`): `GET /health`, `POST /scan`, `POST /jobs`,
`POST /jobs/{job}/upload-pid`, `POST /jobs/{job}/upload-scope`, `POST /jobs/{job}/scan`,
`GET /materials`. A `Dockerfile` is provided (`docker build -t engineering-app . &&
docker run --rm -p 8000:8000 engineering-app`). The API has no interactive review or
question flow; that lives in the desktop app.

## Known limitations

- Valve, flange and fitting **symbols without text labels cannot be counted**; they appear as scope-only rows with a page or equipment location.
- Piping is listed by size as runs, not footage (no drawing scale is measured).
- Colour/boldness detection assumes the green/red/blue markup convention; other conventions fall back to "highlighted, or named in scope".
- Scanned drawings without a text layer need OCR, which is not implemented.

## Roadmap

See [`IMPLEMENTATION_ROADMAP.md`](IMPLEMENTATION_ROADMAP.md) for what is done and what is next.

## License

No license has been specified yet.

## Using other drawings and vocabulary

Nothing is tied to a particular drawing. Codes come from each drawing's own legend and from tag prefixes repeated on its pages. To add your own codes, place a `vocabulary.json` next to the program:

```json
{"codes": {"XYZ": "Custom Device"}, "ignore_prefixes": ["DWG"], "scope_aliases": {"Pneumatic Valve": ["POV"]}}
```
