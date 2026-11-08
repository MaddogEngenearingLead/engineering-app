# Engineering App – P&ID vs Scope-of-Work BOM

A desktop app that reads a P&ID drawing (PDF), compares it with a scope-of-work
document, and produces a bill of materials (BOM) containing only what the scope
calls for. Drawing processing and OCR run locally, and there are no app accounts
or login. Every scan uses AI: the configured provider is tried first, with bundled
local Ollama used only if that provider is unavailable or fails. Ollama starts
automatically and downloads its vision model on first launch. The app also contacts
GitHub to check for updates.

## How it works

1. **Create a job** – enter a job number and drop in the P&ID PDF and, if available, the scope (Word, PDF or text).
2. **Generate the BOM** – the app:
   - detects demo, new-work and legend pages and the markup colour convention
     (green = new, red = demo, blue clouds = future, bold = in scope, grey = existing);
   - counts tagged items on the new-work pages and records a drawing location
     (page and grid, e.g. `p4 D-12`) for each;
   - keeps an item only if it is new work **and** the scope refers to it (by tag, code or name);
   - adds scope-only rows for work the scope lists but the drawing cannot count
     (valves, flanges, supports), anchored to a page or nearby equipment;
   - flags highlighted line markup for review instead of assuming it is piping
     or assigning a nearby size to a component.
   - when a drawing package contains a printed BOM, reads it as the master list
     instead, preserving all rows and flagging scope matches for review.
   - if no scope file exists, prepares an editable draft listing identified items,
     drawing quantities, stated supply/installation responsibilities and explicitly
     referenced work notes where available. Unlinked notes and items with no
     identified instruction remain clearly marked for review. Review and edit
     it against the P&ID, then approve
     it before the app saves `scope/reviewed_scope.txt` and reruns the scan.
     Cancelling leaves the draft pending and does not create a scope file.
   - compares matching tag labels on demo and new-work pages for review. A matching
     tag does not establish a replacement, and tag coordinates mark labels rather
     than necessarily the physical components. Scope materials with no stated
     quantity remain blank; separate work areas are retained for review.
     Review the required connections and ancillary materials against the complete
     drawings and specifications: the app cannot determine a complete takeoff.
     When a printed BOM is extracted, it is treated as a master list, not proof
     of scope; automatic demo/new tag comparison is not performed on that path.
3. **Review / clarify** – open the review window to:
   - see every item with its location and why it is on the BOM;
   - use **Show on drawing** with Previous/Next and zoom to look at each location;
     a magenta circle marks the selected location without obscuring its center.
     When only a page is known, the viewer shows the whole page without a circle;
     question locations show a scrollable note identifying the item, what is being
     asked, and why. The note changes with the selected location;
     unrecognised tags can be located this way after rescanning older jobs;
     page-only warnings open the whole page without a guessed circle; zoom and
     drag to inspect it. Drag the review note by its heading to reposition it,
     or hide it when it obscures the drawing;
     scope-only item locations may indicate nearby references rather than the
     component itself; these are explicitly identified in the viewer;
     printed BOM locations indicate the table row, not a confirmed component
     location on another sheet. Tagged locations identify text labels. Use
     **Mark item location** in BOM review to select a drawing page and mark the
     actual component; save the review to retain the user-marked location;
     for a scan that needs clarification before a BOM can be generated, use
     **View drawing issues** to inspect warnings with known drawing locations;
   - answer the **questions** the scan could not settle (marked `[OPEN]` / `[answered]`).
     Each question says what is asked, why, and where on the drawing. Answers add or
     change BOM items and are recorded on the BOM; answered questions stop being flagged.
     Answers are kept if the BOM is regenerated;
   - edit, remove or add items and add free-text clarification notes.
4. **Save and re-export** – the BOM PDF (items, locations, clarifications, remaining
   review notes) is rewritten. Only the most recent successfully generated job
   BOM PDF, CSV and JSON are kept in `bom_exports/`; other files are not removed.
   The PDF lists materials before an extractive, bulleted scope summary, limited
   to 12 statements when the source is long. JSON retains the complete scope and
   all extracted summary statements. Verify the summary against the original
   scope document, particularly exclusions and qualifications.

To permanently remove a job, select **Delete job** on its dashboard row and
confirm. The job folder, including its copied drawings, scope, BOMs and review
data, is deleted; original files outside the job folder are not. Wait for any
running scan to finish before deleting.

Nothing is specific to one drawing or scope; the files used during development are
test data only.

## Install (end users)

Download the latest release from the repository's **Releases** page:

- **Windows:** `JobManager-windows.zip` (unzip the folder and run `JobManager.exe`; no Python needed).
- **macOS:** `JobManager-macos.zip` (unzip and open `JobManager.app`).

**Portable use (USB drive, Windows):** unzip the full app folder onto the drive and run `JobManager.exe`;
jobs are saved in a
`Jobs` folder next to it, so they travel with the program. On a normal hard drive, create an empty
`Jobs` folder beside the exe to get the same behaviour; otherwise jobs live in
`%LOCALAPPDATA%\EngineeringApp\uploads`. Existing jobs are not moved automatically; copy that
folder's contents into `Jobs` if you want them on the drive.

Updates: the app checks for a new version at launch and can update itself
(**Check for updates**). Windows releases are folders distributed as ZIP files so the bundled Ollama runtime is not
re-extracted on every launch. The app can overlay updates in place while preserving user files.
Windows installations from v0.1.27 and earlier must manually download and extract this ZIP
for the first update; their updater looks for the former single-file executable.
Releases are built automatically by GitHub Actions
(`.github/workflows/build-gui.yml`) when a `v*` tag is pushed. An optional Windows
installer is described in [`installer/README.md`](installer/README.md).

## Run from source (developers)

Requires Python 3.12 and, on Linux, `python3-tk`.
For image-only BOM sheets and revision areas, OCR runs locally. The updated Windows
and macOS release workflow bundles Tesseract with English language data; releases
published before that workflow is deployed require a separate installation. When
running from source, install Tesseract with English data and make `tesseract`
available on `PATH`. OCR results still require review.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python run_gui.py                # or: python -m app.gui
python -m pytest tests -q        # run the tests
python run_gui.py --selftest     # headless scan + review-save check (used by CI)
```

Build the app on the target OS after preparing Ollama with
`python scripts/prepare_ollama_bundle.py --output build/ollama-bundle` and setting
`OLLAMA_BUNDLE_DIR` to `build/ollama-bundle/ollama-runtime`; then run
`pip install pyinstaller && python build_exe.py`
(`dist/JobManager/JobManager.exe` on Windows, `dist/JobManager.app` on macOS).

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
    scope_work.py          # scope summaries and reviewed drawing-derived drafts
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
`GET /materials`. When a job scan returns `needs_scope_review`, retrieve the draft
with `GET /jobs/{job}/scope-draft`, review and edit it, then submit it as form
field `scope_of_work` to `POST /jobs/{job}/scope-draft/approve`. Scan again to
generate a BOM using the approved file. The draft is evidence for review, not
proof that work is authorized; scanned drawings without readable text may
require the user to write the scope. The one-off `/scan` has no job scope file.
Other interactive BOM review and questions live in the desktop app. A `Dockerfile`
is provided (`docker build -t engineering-app . && docker run --rm -p 8000:8000 engineering-app`).

## Known limitations

- Valve, flange and fitting **symbols without text labels cannot be counted**; they appear as scope-only rows with a page or equipment location.
- Piping is listed by size as runs, not footage (no drawing scale is measured).
- Colour/boldness detection assumes the green/red/blue markup convention; other conventions fall back to "highlighted, or named in scope".
- OCR is limited to identifying image-only BOM sheets and revision areas. OCR text
  and reconstructed table rows require manual verification; other scanned drawing
  content, tags, and symbols are not read by OCR. Complex or low-resolution
  tables may not reconstruct; use a text-layer PDF or check the source manually.

## Roadmap

See [`IMPLEMENTATION_ROADMAP.md`](IMPLEMENTATION_ROADMAP.md) for what is done and what is next.

## License

No license has been specified yet.

## Using other drawings and vocabulary

Nothing is tied to a particular drawing. Codes come from each drawing's own legend and from tag prefixes repeated on its pages. To add your own codes, place a `vocabulary.json` next to the program:

```json
{"codes": {"XYZ": "Custom Device"}, "ignore_prefixes": ["DWG"], "scope_aliases": {"Pneumatic Valve": ["POV"]}}
```

For printed BOMs, `scope_aliases` also maps a scope term to words in material
descriptions, for example `"Jointing": ["GASKET"]`. Built-in bulk-material
aliases cover flanges, gaskets, bolts, nuts, bolting, pipe, valves and several
other material classes. The scope-crosscheck question can show each printed row
and its matched term and scope excerpt, or explain that no term matched. Native
table rows are circled; OCR and AI rows may only have a page-level location.
Rescan older jobs to collect row coordinates and match evidence. A terminology match does
not verify size, rating, quantity, responsibility or whether work is in scope:
all printed rows remain in the master list for review. Unstated quantities are
left blank instead of assumed to be one.

## AI review and local fallback

Open **Help** on the dashboard for setup instructions, examples and troubleshooting.
Before scanning, click **AI settings** on the dashboard and select Google Gemini, ChatGPT (OpenAI API),
Anthropic Claude, xAI Grok, Groq, Mistral AI, OpenRouter, Together AI, or an
OpenAI-compatible provider, and enter that provider's API key and a vision-capable
model. Grok, Groq, Mistral, OpenRouter and Together require an explicit model ID
that supports image input and the OpenAI chat-completions image format. For a custom
compatible provider, also supply its HTTPS
API base URL (typically ending in `/v1`); the service must support image inputs.
The settings window explains each field and links to the selected provider's
API-key page and model catalog. A key is optional: if the selected provider has no working
configuration, the app uses local Ollama instead.
ChatGPT uses an OpenAI API key and API billing; a ChatGPT subscription does not
include API access.
Available models, costs and image limits depend on the provider. Not every AI
service supports this protocol. Provider keys are stored separately in the local
settings file as plaintext. If the selected cloud provider is unavailable or fails,
the app automatically switches to local Ollama. When no scope is supplied, the app sends
extracted drawing text, BOM rows and its review index to prepare a phased,
source-cited scope draft. Review
and approve all generated scope language before use; matching evidence references
do not establish authorization or prove a complete takeoff. AI's missing/unneeded
item suggestions change nothing until you approve them.

Ollama is bundled with the Windows and macOS apps and starts in the background when the app launches. On first start it downloads `qwen3-vl:4b` (about 3.3 GB) into the app's local data folder; allow disk space and internet access for this one-time download. A configured cloud provider remains primary; Ollama is used only if it is missing or fails. If OCR identifies a BOM page but cannot reconstruct its table, AI also receives overlapping images of that page and attempts a transcription before clarification is requested. If OCR is unavailable, image-only pages are sent for the same attempt. AI-transcribed rows are **unverified**; check every row, quantity, unit, scope and completeness against the drawing. Settings are stored in `%LOCALAPPDATA%\EngineeringApp\ai_settings.json` on Windows, or under `$XDG_CONFIG_HOME/EngineeringApp/` (default `~/.config/EngineeringApp/`) on macOS and Linux.
