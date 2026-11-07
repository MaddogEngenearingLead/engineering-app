# Roadmap

**Product:** a desktop app that compares a P&ID to a scope of work and produces a
scope-accurate BOM, with interactive review. Processing is local by default; optional AI review
sends drawing and scope data to its provider. **Current release: v0.1.20.**

The original plan (FastAPI + Postgres/Mongo/Neo4j/Redis web platform) was replaced by this
desktop-first direction. Databases, queues, OCR services and user accounts were never built and
are not planned for the desktop app; accounts and login were deliberately removed.

Legend: ✅ done · 🟡 partly done · ⬜ not started

## Where we are

| Phase | Theme | Status |
| --- | --- | --- |
| 0 | Foundation (API skeleton, tests, Docker) | ✅ |
| 1 | P&ID vs scope scan restored and verified | ✅ |
| 2 | One-click packaged app and auto-update | ✅ |
| 3 | Scope-accurate item selection and locations | ✅ |
| 4 | Interactive review and clarification | ✅ |
| 5 | Accuracy on more drawings | 🟡 in progress |
| 6 | Quality and distribution polish | ⬜ |

### Phase 0 – Foundation ✅
- FastAPI service (`/api/health`, `/api/scan`, jobs routes), Docker image, pytest suite, browser UI scaffold.

### Phase 1 – Scan restored ✅
- Page classification (demo / new work / legend), colour scheme detection, legend parsing.
- Scope text read from Word, PDF or text; BOM exported as PDF/JSON/CSV.
- Job-based GUI with drag-and-drop, progress and regenerate.

### Phase 2 – Packaging and updates ✅ (v0.1.0–v0.1.2, v0.1.5–v0.1.6)
- PyInstaller one-file Windows exe and macOS app built by GitHub Actions on every `v*` tag, with a
  packaged `--selftest` gate.
- In-app update check, update banner, in-place update; relaunch DLL error fixed (v0.1.5+).
- Local accounts were built and then removed (v0.1.3): local-only, no login.

### Phase 3 – Scope-accurate selection and locations ✅ (v0.1.3–v0.1.4, v0.1.9)
- Item counts match the drawing: label scan with stacked-tag pairing, highlighted-region and
  bold/grey detection, pipe-run joining.
- Only items that are new work **and** referenced by the scope are listed; unreferenced new-work
  items are left off and raised as a question.
- Every item has a location (page + grid); scope-only rows quote the scope section and sentence.
- Markup notes carry context (nearest equipment, pipe size, scope sentence).
- No drawing- or job-specific values in the code (audited in v0.1.5).

### Phase 4 – Interactive review ✅ (v0.1.6–v0.1.10)
- Review window with location viewer: Previous/Next, zoom, whole-page fallback, non-blocking windows.
- Questions with "why am I asking", locations, choice/checklist/form answers; answers change the BOM,
  resolve the flag, appear on the PDF, can be changed, and survive regeneration.
- Dashboard shows only the PDF; CSV/JSON are internal.

### Phase 5 – Accuracy on more drawings 🟡 in progress
- Optional AI fallback reads the drawing index to classify demo and new-work pages (v0.1.18).
- [ ] Run on additional real P&ID/scope pairs and add anonymised fixtures for regression tests.
- [ ] Count unlabelled valve/flange/fitting symbols from the symbol legend (today: scope-only rows).
- [ ] Piping footage: use a scale or let the user mark lengths on the viewer (today: manual entry in a question).
- [ ] Tune the scope-reference matcher (tag/code/name) on more vocabularies; make the threshold configurable.
- [ ] Broaden OCR beyond image-only BOM/revision areas to drawing labels and symbols;
  OCR-extracted BOM rows and revision text still need manual verification.
- [ ] Support other markup conventions (non-green/red/blue) via a user-chosen colour mapping.

### Phase 6 – Quality and distribution ⬜
- [ ] Code-sign the Windows exe / notarise the macOS app to avoid SmartScreen/Gatekeeper warnings.
- [ ] Optional Inno Setup installer built in CI (`installer/`).
- [ ] Automated GUI tests (headless Tk) for the review and question dialogs.
- [ ] Revision comparison: re-scan a revised P&ID and show what changed against the previous BOM.
- [ ] Export options (Excel BOM, per-area grouping) if requested.
- [ ] Decide the fate of the legacy HTTP API and `frontend/` (keep as scripting API, or remove).
