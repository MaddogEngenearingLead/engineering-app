# Engineering App

A full-stack foundation for visualizing and managing process and instrumentation diagram (P&ID) and pipeline engineering data.

The project currently combines a small FastAPI backend with a browser-based HTML/CSS/JavaScript dashboard. It is designed to grow into a document-processing platform for extracting engineering assets, generating bills of materials, and managing engineering workflows.

## Current status

The repository is an early-stage foundation. The backend currently provides health and pipeline-summary endpoints, while the frontend contains dashboard views and browser-local asset management. Python dependencies have been validated and the backend is ready for API development.

See [`IMPLEMENTATION_ROADMAP.md`](IMPLEMENTATION_ROADMAP.md) for the planned implementation phases.

## Features

### Backend

- FastAPI application with automatic OpenAPI documentation
- Health check endpoint
- Pipeline summary endpoint
- Pydantic and environment-configuration dependencies ready for expansion
- Docker image for running the API on port `8000`

### Frontend

- Dashboard overview for engineering assets
- Equipment inventory views
- Pipeline and asset detail pages
- P&ID viewer interface
- BOM generator interface
- Reports and alarms pages
- Responsive styling and light/dark display support
- Browser `localStorage` for the current frontend data model

## Repository structure

```text
.
├── app/
│   ├── main.py                 # FastAPI application entry point
│   ├── api/routes.py           # API routes under /api
│   ├── models/                 # Pipeline data models
│   └── services/               # Pipeline service layer
├── frontend/
│   ├── index.html              # Main dashboard
│   ├── equipment.html          # Equipment inventory
│   ├── asset-details.html      # Asset details
│   ├── pid-viewer.html         # P&ID viewer
│   ├── bom-generator.html      # BOM interface
│   ├── reports.html             # Reports view
│   ├── alarms.html              # Alarms view
│   ├── script.js                # Dashboard behavior
│   ├── pid-visualizer.js        # P&ID visualization behavior
│   ├── bom-generator.js         # BOM interface behavior
│   └── styles.css               # Shared frontend styles
├── Dockerfile
├── IMPLEMENTATION_ROADMAP.md
├── requirements.txt
└── README.md
```

## Requirements

- Python 3.10 or newer
- A modern web browser
- Optional: Docker

## Quick Start: Run Tests from a Fresh Window

### Windows (Git Bash)

```bash
# Clone or navigate to the repository
cd engineering-app

# Create a virtual environment
python -m venv .venv

# Activate the virtual environment (use 'source' in Git Bash)
source .venv/Scripts/activate

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Run tests
python -m pytest tests -q

# View test results summary
```

### macOS / Linux (Bash)

```bash
# Clone or navigate to the repository
cd engineering-app

# Create a virtual environment
python3 -m venv .venv

# Activate the virtual environment
source .venv/bin/activate

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Run tests
python -m pytest tests -q

# View test results summary
```

### Windows (Command Prompt / PowerShell)

```cmd
# Clone or navigate to the repository
cd engineering-app

# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
.venv\Scripts\activate

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Run tests
python -m pytest tests -q

# View test results summary
```

## Run the backend locally

Create and activate a virtual environment, then install the Python dependencies:

```bash
python -m venv .venv
source .venv/bin/activate       # Windows Git Bash: source .venv/Scripts/activate
                                 # Windows CMD: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Start the development server:

```bash
uvicorn app.main:app --reload
```

The API will be available at:

- Root response: <http://localhost:8000/>
- Health check: <http://localhost:8000/api/health>
- Pipeline summary: <http://localhost:8000/api/pipeline>
- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>

### Example API responses

```bash
curl http://localhost:8000/api/health
# {"status":"ok","service":"engineering-app"}

curl http://localhost:8000/api/pipeline
# {"asset_count":0,"status":"initialized","message":"Pipeline monitoring dashboard is ready for configuration."}
```

## Run with Docker

Build and start the API container from the repository root:

```bash
docker build -t engineering-app .
docker run --rm -p 8000:8000 engineering-app
```

Then open <http://localhost:8000/docs> to inspect the API.

## Open the frontend

The frontend is a static dashboard and can be opened directly in a browser:

```bash
# macOS
open frontend/index.html

# Linux
xdg-open frontend/index.html
```

Alternatively, serve it with a local HTTP server:

```bash
python -m http.server 8080 --directory frontend
```

Then open <http://localhost:8080>.

> The current frontend stores its data in browser `localStorage`. It is not yet connected to persistent backend storage.

## API overview

The FastAPI router uses the `/api` prefix:

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/` | Confirms that the API is running |
| `GET` | `/api/health` | Returns service health information |
| `GET` | `/api/pipeline` | Returns the initial pipeline summary |

Interactive API documentation is generated automatically at `/docs` and `/redoc` when the server is running.

## Development notes

- Keep backend code under `app/` and static dashboard assets under `frontend/`.
- Add or update API routes in `app/api/routes.py`.
- The application entry point is `app.main:app`.
- Do not treat roadmap components such as databases, OCR, background workers, and persistent project storage as available until they are implemented and configured.

## Roadmap

Planned work includes:

1. Stabilize local startup and add automated smoke tests.
2. Add P&ID document upload and extraction workflows.
3. Persist projects, documents, scan jobs, equipment, and BOM data.
4. Add OCR, symbol detection, topology analysis, and quality scoring.
5. Connect the frontend to project-scoped API endpoints.
6. Add authentication, review workflows, analytics, and production deployment support.

For the detailed task breakdown and current planning status, see [`IMPLEMENTATION_ROADMAP.md`](IMPLEMENTATION_ROADMAP.md).

## License

No license has been specified yet for this project.

## Desktop GUI

Run the Tkinter Job Manager with `python -m app.gui` (requires `tkinterdnd2`, listed in requirements.txt).

To build a standalone executable (on the target OS): `pip install pyinstaller && python build_exe.py`; output is `dist/JobManager`. Alternatively run `python run_gui.py`.
