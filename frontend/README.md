# Frontend (legacy browser UI)

Static HTML/JS pages (and a React/Vite scaffold under `src/`) for the optional local HTTP API
(`uvicorn app.main:app`). **The desktop app does not use this folder**; the interactive review and
question workflow live only in the desktop app (`app/gui/`).

Open `frontend/bom-generator.html` in a browser, or serve it with
`python -m http.server 8080 --directory frontend`. Dashboard pages store their data in browser
`localStorage` only.

Its future is an open item in [`IMPLEMENTATION_ROADMAP.md`](../IMPLEMENTATION_ROADMAP.md) (Phase 6).
