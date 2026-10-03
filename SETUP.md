# Engineering App - Local Development Setup

## Prerequisites
- Python 3.12
- pip and venv

## Quick Start

```bash
# Create and activate virtual environment
python3.12 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# Start the backend API
uvicorn app.main:app --reload
```

The API will be available at:
- Root: http://localhost:8000/
- Health: http://localhost:8000/api/health
- Pipeline: http://localhost:8000/api/pipeline
- Upload: POST http://localhost:8000/api/upload
- Scan: POST http://localhost:8000/api/scan
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Testing Endpoints

### Health Check
```bash
curl http://localhost:8000/api/health
```

### Upload a File
```bash
curl -X POST "http://localhost:8000/api/upload" \
  -F "file=@path/to/sample.pdf"
```

### Scan a File
```bash
curl -X POST "http://localhost:8000/api/scan" \
  -F "file=@path/to/sample.pdf"
```

### Get Materials
```bash
curl http://localhost:8000/api/materials
```

### Get Job Status
```bash
curl http://localhost:8000/api/jobs/job-0001
```

## File Upload

Supported file types:
- PDF (.pdf)
- Images (.png, .jpg, .jpeg, .gif, .svg)

Maximum file size: 25 MB

Uploaded files are saved to: `backend/uploads/`

## Environment Configuration

Create a `.env` file to override defaults:

```bash
APP_NAME=engineering-app
ENVIRONMENT=development
UPLOAD_DIR=backend/uploads
MAX_UPLOAD_SIZE_MB=25
CORS_ORIGINS=["*"]
```

## Frontend

Open the frontend dashboard:
```bash
open frontend/bom-generator.html
```

Or serve with Python:
```bash
python -m http.server 8080 --directory frontend
```

Then open: http://localhost:8080/frontend/bom-generator.html

## Troubleshooting

**Port 8000 already in use:**
```bash
uvicorn app.main:app --reload --port 8001
```

**ModuleNotFoundError:**
- Ensure virtual environment is activated
- Re-run: `pip install -r requirements.txt`

**File upload fails:**
- Check that `backend/uploads/` directory exists and is writable
- Verify file size is under 25 MB
- Ensure file extension is supported

## Next Steps

See `IMPLEMENTATION_ROADMAP.md` for the full Phase 1 and Phase 2 implementation plan.
