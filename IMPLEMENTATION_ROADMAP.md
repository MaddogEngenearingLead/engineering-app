# Engineering P&ID Platform - Implementation Roadmap

## Project Overview

This document tracks the implementation of the P&ID engineering document processing platform. The platform enables users to:
- Upload P&ID documents (PDF, PNG, JPG)
- Automatically extract equipment tags, types, and connections
- Generate bill of materials (BOM) from extracted data
- Store and manage engineering projects with persistent results
- Review and validate extracted information

## Current Project Status

### Completed Components
- ✅ Backend API structure (FastAPI)
- ✅ AI pipeline framework (OCR, symbol detection)
- ✅ PDF parsing engine (pdfplumber-based text extraction, table detection)
- ✅ Docker Compose local orchestration
- ✅ Frontend BOM UI and file upload interface
- ✅ Extraction quality enhancement layer
- ✅ Universal document processor (PDF + image routing)
- ✅ Engineering text normalization and tag pattern matching

### Architecture Components

**Backend:**
- FastAPI application with CORS middleware
- Route handlers for upload, scan, materials, jobs, projects
- Service layer for PID processing
- Job store for in-memory result tracking

**AI Pipeline:**
- PDF processor (text extraction, table parsing, page conversion)
- OCR engine for image-based documents
- Symbol detector for equipment identification
- Graph builder for topology analysis
- Extraction quality scorer and document assessor

**Data Layer:**
- PostgreSQL (transactional app data - planned)
- MongoDB (raw extraction artifacts - planned)
- Neo4j (equipment topology graph - planned)
- Redis (job queue - planned)

**Infrastructure:**
- Docker Compose with postgres, mongo, neo4j, redis, backend, worker
- File upload storage to local filesystem
- Environment-based configuration

**Frontend:**
- Single-page HTML interface with drag-drop upload
- Real-time scan results rendering
- BOM table with equipment inventory
- Export capabilities (CSV, JSON)

---

## Phase 1: Stabilize and Run the Project Locally

**Objective:** Get the full stack running without import/runtime errors. Confirm the backend, AI worker, and data services can start together. Verify the upload → scan flow works on a sample document.

### 1. Dependency and Import Validation

**Status:** ⏳ NOT STARTED

**Description:** Audit and fix all package dependencies and imports.

**Tasks:**
- [ ] Audit backend/requirements.txt for Python 3.12 compatibility
- [ ] Audit backend/requirements-db.txt (psycopg2, sqlalchemy, alembic)
- [ ] Audit ai_pipeline/requirements.txt (pdfplumber, opencv, tesseract, PyMuPDF)
- [ ] Run `python -m compileall backend ai_pipeline` to check for syntax errors
- [ ] Fix any import errors in backend/app/main.py
- [ ] Fix any import errors in backend/app/api/routes.py
- [ ] Fix any import errors in backend/app/services/pid_processing.py
- [ ] Fix any import errors in ai_pipeline/pdf_pipeline.py
- [ ] Fix any import errors in ai_pipeline/universal_processor.py
- [ ] Test: `python -c "from app.main import app; print('backend ok')"`
- [ ] Test: `python -c "from ai_pipeline.universal_processor import process_pid_file_universal; print('ai ok')"`
- [ ] Resolve any circular imports or duplicate route registrations
- [ ] Verify all pdfplumber, opencv, tesseract optional dependencies are available

**Acceptance Criteria:**
- All imports succeed without ModuleNotFoundError or ImportError
- No syntax errors in any Python file
- Both backend and AI pipeline can be imported in a clean Python 3.12 environment

**Notes:**
- Run in a fresh virtual environment to ensure clean state
- Document any version conflicts found
- Consider updating requirements.txt with pinned versions if needed

---

### 2. Fix App Startup and Configuration

**Status:** ⏳ NOT STARTED

**Description:** Validate and fix environment variable handling and configuration settings.

**Tasks:**
- [ ] Review backend/app/core/config.py for all required settings
- [ ] Ensure `app_name`, `environment`, `api_prefix`, `upload_dir`, `max_upload_size_mb`, `cors_origins` are defined
- [ ] Add environment variable support for:
  - `DATABASE_URL` (default: postgresql://postgres:postgres@localhost:5432/engineering_pid)
  - `MONGODB_URL` (default: mongodb://localhost:27017)
  - `NEO4J_URL` (default: bolt://localhost:7687)
  - `REDIS_URL` (default: redis://localhost:6379/0)
  - `UPLOAD_DIR` (default: backend/uploads)
  - `APP_ENV` (default: development)
- [ ] Verify upload directory path resolves to writable location
- [ ] Create upload directory if it doesn't exist
- [ ] Test config loads without errors
- [ ] Add logging statements for config values on startup
- [ ] Ensure CORS is set to allow localhost:* for local development
- [ ] Add health check endpoint verification in startup

**Acceptance Criteria:**
- Config values are read from environment or use sensible defaults
- Upload path is created and writable
- No config-related errors on app startup
- Settings are logged for visibility

**Notes:**
- Use python-dotenv for .env file support
- Consider adding a .env.example file for documentation

---

### 3. Validate All Services and Service Dependency Order

**Status:** ⏳ NOT STARTED

**Description:** Confirm Docker Compose orchestration works correctly.

**Tasks:**
- [ ] Review docker-compose.yml for correct service ordering
- [ ] Ensure `depends_on` directives are set correctly
- [ ] Verify all services have correct port mappings:
  - postgres: 5432
  - mongo: 27017
  - neo4j: 7474, 7687
  - redis: 6379
  - backend: 8000
- [ ] Add health checks to docker-compose.yml for:
  - postgres (pg_isready)
  - mongo (mongosh --eval)
  - neo4j (HTTP health endpoint)
  - redis (redis-cli ping)
- [ ] Create scripts/start-local.sh for easy startup
- [ ] Create scripts/stop-local.sh for cleanup
- [ ] Create scripts/check-health.sh to verify all services
- [ ] Create Makefile targets:
  - `make start` - start all services
  - `make stop` - stop all services
  - `make health` - check service health
  - `make logs` - view logs
- [ ] Test startup sequence: `docker compose up --build`
- [ ] Verify no crashes during startup
- [ ] Verify all services are reachable on expected ports

**Acceptance Criteria:**
- `docker compose up` starts all services without fatal errors
- Each service is reachable on its expected port within 30 seconds
- Health checks pass for all services
- Services can be cleanly stopped without errors

**Notes:**
- Consider adding wait-for-it.sh script for dependency ordering
- Document expected startup time

---

### 4. Smoke Test the API

**Status:** ⏳ NOT STARTED

**Description:** Test all core API endpoints with sample data.

**Tasks:**
- [ ] Prepare test files:
  - tiny PNG image (50x50px)
  - tiny PDF file (single page, simple text)
- [ ] Start backend API locally: `uvicorn app.main:app --reload`
- [ ] Test GET /api/health
  - Expected: {"status":"ok","service":"engineering-pid-api","environment":"development"}
  - Status: ⏳
- [ ] Test POST /api/upload with PNG
  - Expected: {"message":"File uploaded successfully.","filename":...,"saved_path":...,"size_bytes":...}
  - Status: ⏳
- [ ] Test POST /api/upload with PDF
  - Expected: Same structure as PNG test
  - Status: ⏳
- [ ] Verify file is saved to disk
  - Check backend/uploads/ directory
  - Status: ⏳
- [ ] Test POST /api/scan with PNG
  - Expected: {"job_id":...,"status":"completed","detected_assets":[...],"materials":[...],"total_items":...,"estimated_total_cost":...}
  - Status: ⏳
- [ ] Test POST /api/scan with PDF
  - Expected: Same structure with multi-page data if applicable
  - Status: ⏳
- [ ] Test GET /api/materials
  - Expected: {"materials":[...],"total_items":...,"estimated_total_cost":...}
  - Status: ⏳
- [ ] Test GET /api/jobs/{job_id}
  - Expected: {"job_id":...,"status":"completed","progress":100,"message":...,"source_file":...}
  - Status: ⏳
- [ ] Test error handling:
  - POST /api/upload without file (expected: 400)
  - POST /api/upload with unsupported type (expected: 400)
  - POST /api/upload with oversized file (expected: 413)
  - GET /api/jobs/invalid-id (expected: 404)
  - Status: ⏳
- [ ] Verify no unhandled exceptions in API logs
- [ ] Confirm all responses are valid JSON

**Acceptance Criteria:**
- All happy-path API calls return HTTP 200 with expected JSON
- Error cases return appropriate HTTP status codes
- No unhandled exceptions occur
- Uploaded files are persisted on disk
- Scan results contain non-empty equipment/materials

**Notes:**
- Use curl, Postman, or Python requests for testing
- Document API responses for reference

---

### 5. Fix Frontend-to-Backend Compatibility

**Status:** ⏳ NOT STARTED

**Description:** Ensure the frontend can communicate with the backend API.

**Tasks:**
- [ ] Review frontend/bom-generator.html
- [ ] Verify HTML form and file input elements exist
- [ ] Review frontend/bom-generator.js
- [ ] Check API base URL: `const API_BASE = 'http://localhost:8000/api'`
- [ ] Verify fetch calls use correct endpoints:
  - `/api/scan` for file upload
  - Response structure matches: `data.detected_assets`, `data.materials`
- [ ] Verify response field mappings:
  - Equipment: `tag`, `type`, `confidence`
  - Materials: `item_number`, `tag_id`, `description`, `type`, `quantity`, `unit`, `supplier`, `unit_cost`, `total_cost`
- [ ] Test drag-drop file upload in browser
- [ ] Test file input click-to-select in browser
- [ ] Verify CORS headers are set correctly in backend (allow localhost)
- [ ] Test in browser console for errors
- [ ] Verify UI states:
  - Initial state: upload zone visible
  - Scanning state: loading indicator
  - Results state: equipment list and BOM table
- [ ] Test export functionality (CSV, JSON)
- [ ] Verify no CORS errors in browser Network tab

**Acceptance Criteria:**
- Frontend loads without errors
- File upload from browser triggers backend scan
- Frontend renders detected assets and BOM without console errors
- All form inputs and export buttons work
- No CORS issues

**Notes:**
- Open frontend/bom-generator.html in a modern browser
- Use browser DevTools Network tab to inspect API calls
- Ensure backend is running on localhost:8000

---

### 6. Phase 1 Deliverable Validation

**Status:** ⏳ NOT STARTED

**Description:** Confirm all Phase 1 objectives are met.

**Checklist:**
- [ ] Local Python environment with Python 3.12 is working
- [ ] All dependencies install cleanly without conflicts
- [ ] Backend imports successfully without errors
- [ ] AI pipeline imports successfully without errors
- [ ] FastAPI app starts without errors
- [ ] Health endpoint responds with 200 OK
- [ ] Upload route accepts files and saves to disk
- [ ] Scan route processes files and returns structured results
- [ ] Materials route returns valid BOM payload
- [ ] Jobs route returns job status and metadata
- [ ] Docker Compose can start all local services
- [ ] All services are reachable on expected ports
- [ ] Frontend can upload files and render backend results
- [ ] No fatal startup or runtime errors remain
- [ ] Sample file successfully processes through full pipeline
- [ ] Documentation exists for local startup procedure

**Acceptance Criteria:**
- All items checked
- No blockers or unresolved errors
- Project runs reliably in a fresh environment

---

## Phase 2: Add Real Persistence and Data Flow

**Objective:** Persist uploaded files, jobs, extracted equipment, and BOM output to persistent storage. Connect the workflow from upload to stored results in a database-backed system.

### 1. Finalize Core Data Model

**Status:** ⏳ NOT STARTED

**Description:** Define the canonical data model for projects, documents, jobs, and results.

**Database Selection:**
- **PostgreSQL:** Transactional app data (projects, documents, jobs, equipment, materials)
- **MongoDB:** Raw processing artifacts (OCR results, extraction payloads, quality scores)
- **Neo4j:** Equipment topology and relationships (nodes, connections, flow directions)

**Tasks:**
- [ ] Create backend/app/models/database.py with SQLAlchemy ORM models
- [ ] Create backend/app/models/schemas.py with Pydantic schemas
- [ ] Create backend/app/database/repositories.py with CRUD patterns
- [ ] Create backend/app/database/postgres.py with connection pooling
- [ ] Define Project model:
  - id (UUID, primary key)
  - name (string, required)
  - description (string, optional)
  - status (enum: active, archived, review_required)
  - created_at (timestamp)
  - updated_at (timestamp)
  - Status: ⏳
- [ ] Define Document model:
  - id (UUID, primary key)
  - project_id (FK to Project)
  - original_filename (string)
  - storage_path (string)
  - mime_type (string)
  - file_size (integer, bytes)
  - file_hash (string, SHA256 for dedup)
  - status (enum: uploaded, processing, processed, failed)
  - uploaded_at (timestamp)
  - processed_at (timestamp, nullable)
  - Status: ⏳
- [ ] Define ScanJob model:
  - id (UUID, primary key)
  - document_id (FK to Document)
  - status (enum: queued, processing, completed, failed)
  - started_at (timestamp)
  - completed_at (timestamp, nullable)
  - error_message (string, nullable)
  - quality_score (float 0-1)
  - result_summary (JSON)
  - Status: ⏳
- [ ] Define Equipment model:
  - id (UUID, primary key)
  - project_id (FK to Project)
  - document_id (FK to Document)
  - tag (string, indexed)
  - name (string)
  - equipment_type (enum: pump, valve, vessel, compressor, filter, tank, heat_exchanger, instrument, motor, equipment)
  - confidence (float 0-1)
  - x (float, coordinate on page)
  - y (float, coordinate on page)
  - page_number (integer)
  - source_text (text, optional)
  - created_at (timestamp)
  - Status: ⏳
- [ ] Define EquipmentConnection model:
  - id (UUID, primary key)
  - project_id (FK to Project)
  - source_tag (FK to Equipment)
  - target_tag (FK to Equipment)
  - connection_type (enum: pipe, electrical, control)
  - flow_direction (enum: forward, reverse, bidirectional)
  - created_at (timestamp)
  - Status: ⏳
- [ ] Define BOMMaterial model:
  - id (UUID, primary key)
  - project_id (FK to Project)
  - document_id (FK to Document)
  - tag (string, indexed)
  - description (string)
  - quantity (integer)
  - unit (string: ea, m, kg, etc.)
  - equipment_type (string)
  - supplier (string, optional)
  - unit_cost (float, optional)
  - total_cost (float, optional)
  - notes (text, optional)
  - created_at (timestamp)
  - Status: ⏳
- [ ] Define ExtractionResult model (MongoDB, BSON):
  - document_id (reference)
  - scan_job_id (reference)
  - file_type (pdf or image)
  - pages_processed (integer)
  - text_blocks (array of {text, confidence, bbox, page})
  - detected_symbols (array of {tag, type, label, confidence, center, page})
  - tables (array of table data)
  - quality_assessment (object)
  - Status: ⏳
- [ ] Create Pydantic schemas for API request/response:
  - ProjectCreate, ProjectResponse
  - DocumentCreate, DocumentResponse
  - EquipmentCreate, EquipmentResponse
  - BOMMaterialCreate, BOMMaterialResponse
  - Status: ⏳

**Acceptance Criteria:**
- All models are clearly defined with proper relationships
- Schema handles all planned use cases
- Models separate transactional data from artifacts
- Documentation explains each field's purpose

**Notes:**
- Use SQLAlchemy for ORM and Alembic for migrations
- Use pymongo for MongoDB interactions
- Use py2neo or similar for Neo4j interactions

---

### 2. Add Database Migrations and Initialization

**Status:** ⏳ NOT STARTED

**Description:** Set up Alembic for schema versioning and create initialization scripts.

**Tasks:**
- [ ] Initialize Alembic: `alembic init alembic`
- [ ] Configure alembic.ini to use SQLALCHEMY_DATABASE_URL from settings
- [ ] Create initial migration:
  - `alembic revision --autogenerate -m "Initial schema"`
  - Status: ⏳
- [ ] Create migration for projects table
  - `alembic revision --autogenerate -m "Create projects table"`
  - Status: ⏳
- [ ] Create migration for documents table
  - `alembic revision --autogenerate -m "Create documents table"`
  - Status: ⏳
- [ ] Create migration for scan_jobs table
  - `alembic revision --autogenerate -m "Create scan_jobs table"`
  - Status: ⏳
- [ ] Create migration for equipment table
  - `alembic revision --autogenerate -m "Create equipment table"`
  - Status: ⏳
- [ ] Create migration for equipment_connections table
  - `alembic revision --autogenerate -m "Create equipment_connections table"`
  - Status: ⏳
- [ ] Create migration for materials table
  - `alembic revision --autogenerate -m "Create materials table"`
  - Status: ⏳
- [ ] Add indexes for commonly queried fields (project_id, tag, document_id)
  - Status: ⏳
- [ ] Create backend/scripts/init_db.py to run migrations on startup
- [ ] Test migrations in local environment
- [ ] Add migration status check to health endpoint

**Acceptance Criteria:**
- All migrations apply successfully
- Tables are created with correct schema
- Indexes are created for performance
- New environments can initialize DB without manual SQL
- Migration history is tracked and reversible

**Notes:**
- Keep migrations in version control
- Test migrations are reversible (alembic downgrade)
- Document migration strategy in README

---

### 3. Persist Uploaded Files and Project Metadata

**Status:** ⏳ NOT STARTED

**Description:** Store uploaded files and their metadata in persistent storage.

**Tasks:**
- [ ] Create ProjectRepository with methods:
  - [ ] create_project(name, description) -> Project
  - [ ] get_project(id) -> Project
  - [ ] list_projects() -> List[Project]
  - [ ] update_project(id, **kwargs) -> Project
  - Status: ⏳
- [ ] Create DocumentRepository with methods:
  - [ ] create_document(project_id, filename, path, mime_type, size) -> Document
  - [ ] get_document(id) -> Document
  - [ ] list_documents_by_project(project_id) -> List[Document]
  - [ ] update_document_status(id, status) -> Document
  - Status: ⏳
- [ ] Modify POST /api/upload to:
  - [ ] Accept project_id parameter (or create default)
  - [ ] Create Project if not provided
  - [ ] Save file to disk
  - [ ] Insert Document row in database
  - [ ] Return document_id and project_id in response
  - Status: ⏳
- [ ] Add POST /api/projects endpoint:
  - [ ] Request: {"name": string, "description": string}
  - [ ] Response: {"id": uuid, "name": string, ...}
  - Status: ⏳
- [ ] Add GET /api/projects endpoint:
  - [ ] Response: {"projects": [{"id": uuid, "name": string, ...}]}
  - Status: ⏳
- [ ] Add GET /api/projects/{project_id} endpoint:
  - [ ] Response: {"id": uuid, "name": string, "documents": [...]}
  - Status: ⏳
- [ ] Update file path handling to include project_id:
  - [ ] backend/uploads/{project_id}/{document_id}/{filename}
  - Status: ⏳
- [ ] Add file storage metadata:
  - [ ] file_hash (SHA256)
  - [ ] original_filename
  - [ ] mime_type
  - [ ] file_size
  - Status: ⏳

**Acceptance Criteria:**
- Each uploaded file has a persisted metadata record
- Files are organized by project and document ID
- Project and document relationships are maintained
- Upload endpoint returns document_id for later retrieval
- No duplicate file storage (via hash checking)

**Notes:**
- Consider implementing soft deletes for documents
- Store file hashes for deduplication
- Document folder structure in README

---

### 4. Persist Scan Jobs and Status Lifecycle

**Status:** ⏳ NOT STARTED

**Description:** Track scan jobs through their lifecycle with persistent state.

**Tasks:**
- [ ] Create ScanJobRepository with methods:
  - [ ] create_scan_job(document_id) -> ScanJob
  - [ ] get_scan_job(id) -> ScanJob
  - [ ] update_scan_job_status(id, status, **kwargs) -> ScanJob
  - [ ] list_scan_jobs_by_document(document_id) -> List[ScanJob]
  - [ ] list_scan_jobs_by_project(project_id) -> List[ScanJob]
  - Status: ⏳
- [ ] Modify POST /api/scan to:
  - [ ] Upload file first (if not already uploaded)
  - [ ] Create ScanJob with status='processing'
  - [ ] Call AI processor
  - [ ] Update ScanJob status to 'completed' or 'failed'
  - [ ] Store result_summary JSON
  - [ ] Return job_id and results
  - Status: ⏳
- [ ] Add POST /api/projects/{project_id}/documents/{document_id}/scan endpoint:
  - [ ] Creates and returns a scan job
  - [ ] Status: ⏳
- [ ] Add GET /api/jobs endpoint:
  - [ ] List all jobs (with pagination)
  - [ ] Status: ⏳
- [ ] Add GET /api/jobs/{job_id} endpoint:
  - [ ] Return full job details including status and results
  - [ ] Status: ⏳
- [ ] Add GET /api/projects/{project_id}/jobs endpoint:
  - [ ] List jobs for a project
  - [ ] Status: ⏳
- [ ] Implement job status lifecycle:
  - [ ] queued -> processing -> completed (or failed)
  - [ ] Store started_at and completed_at timestamps
  - [ ] Store error_message if failed
  - Status: ⏳
- [ ] Replace in-memory JOB_STORE with database queries
  - Status: ⏳

**Acceptance Criteria:**
- Jobs are persisted and queryable after creation
- Job status transitions are tracked
- Job results are stored with complete metadata
- Jobs can be retrieved by ID, document ID, or project ID
- Job history is available for review

**Notes:**
- Job results should be stored as JSON in result_summary field
- Consider adding job retry logic for Phase 3

---

### 5. Persist Extracted Equipment and BOM Results

**Status:** ⏳ NOT STARTED

**Description:** Store extracted equipment and BOM data from scans.

**Tasks:**
- [ ] Create EquipmentRepository with methods:
  - [ ] create_equipment(project_id, document_id, tag, name, type, confidence, x, y, page) -> Equipment
  - [ ] get_equipment(id) -> Equipment
  - [ ] list_equipment_by_document(document_id) -> List[Equipment]
  - [ ] list_equipment_by_project(project_id) -> List[Equipment]
  - [ ] get_equipment_by_tag(project_id, tag) -> Equipment
  - Status: ⏳
- [ ] Create BOMMaterialRepository with methods:
  - [ ] create_bom_material(project_id, document_id, tag, description, quantity, unit, type, supplier, unit_cost, total_cost) -> BOMMaterial
  - [ ] get_bom_material(id) -> BOMMaterial
  - [ ] list_bom_materials_by_document(document_id) -> List[BOMMaterial]
  - [ ] list_bom_materials_by_project(project_id) -> List[BOMMaterial]
  - Status: ⏳
- [ ] Modify process_uploaded_pid() to save extracted data:
  - [ ] After AI processing, extract equipment list
  - [ ] For each equipment item, call create_equipment()
  - [ ] For each BOM item, call create_bom_material()
  - [ ] Return IDs of stored objects
  - Status: ⏳
- [ ] Add GET /api/projects/{project_id}/equipment endpoint:
  - [ ] Return all equipment for project
  - [ ] Response: {"equipment": [{"id": uuid, "tag": string, "type": string, ...}]}
  - Status: ⏳
- [ ] Add GET /api/projects/{project_id}/documents/{document_id}/equipment endpoint:
  - [ ] Return equipment extracted from single document
  - [ ] Status: ⏳
- [ ] Add GET /api/projects/{project_id}/bom endpoint:
  - [ ] Return aggregated BOM for project
  - [ ] Response: {"materials": [{...}], "total_items": int, "total_cost": float}
  - Status: ⏳
- [ ] Add GET /api/projects/{project_id}/documents/{document_id}/bom endpoint:
  - [ ] Return BOM extracted from single document
  - [ ] Status: ⏳
- [ ] Add GET /api/equipment/{equipment_id} endpoint:
  - [ ] Return detailed equipment information
  - [ ] Status: ⏳
- [ ] Add equipment deduplication logic:
  - [ ] Avoid storing same tag multiple times per project
  - [ ] Update existing equipment if re-scanned
  - [ ] Status: ⏳

**Acceptance Criteria:**
- Extracted equipment is saved to database after each scan
- BOM materials are saved to database after each scan
- Equipment can be queried by document, project, or tag
- BOM data is retrievable for reporting and review
- Deduplication prevents duplicate entries

**Notes:**
- Equipment from same project with same tag should be merged
- Consider tagging which scan produced which equipment
- Add soft deletes or version history for equipment changes

---

### 6. Persist Raw Processing Artifacts in MongoDB

**Status:** ⏳ NOT STARTED

**Description:** Store complete extraction payloads and intermediate results.

**Tasks:**
- [ ] Create MongoDBClient wrapper in backend/app/database/mongodb.py
- [ ] Create ExtractionResultRepository with methods:
  - [ ] save_extraction_result(document_id, scan_job_id, result_payload) -> str (object_id)
  - [ ] get_extraction_result(document_id) -> dict
  - [ ] list_extraction_results_by_project(project_id) -> List[dict]
  - Status: ⏳
- [ ] Define MongoDB collection structures:
  - [ ] processing_jobs: {document_id, scan_job_id, file_type, pages_processed, timestamp}
  - [ ] raw_extractions: {document_id, scan_job_id, text_blocks, symbols, tables, quality_score, timestamp}
  - [ ] symbol_detections: {document_id, scan_job_id, page_number, detections, timestamp}
  - [ ] bom_snapshots: {document_id, scan_job_id, bom_items, timestamp}
  - Status: ⏳
- [ ] Modify process_uploaded_pid() to save to MongoDB:
  - [ ] After pipeline completes, insert raw extraction result
  - [ ] Store complete pipeline_output JSON
  - [ ] Include quality assessment
  - [ ] Include timestamp and scan_job_id
  - Status: ⏳
- [ ] Add GET /api/projects/{project_id}/documents/{document_id}/raw-extraction endpoint:
  - [ ] Return raw extraction results from MongoDB
  - [ ] Response: {"text_blocks": [...], "tables": [...], "quality_score": float, ...}
  - Status: ⏳
- [ ] Add GET /api/projects/{project_id}/documents/{document_id}/extraction-history endpoint:
  - [ ] Return all extraction attempts for document
  - [ ] Show progression/versions
  - [ ] Status: ⏳
- [ ] Implement data retention policy:
  - [ ] Keep raw extractions indefinitely (or configure TTL)
  - [ ] Archive old versions
  - [ ] Status: ⏳

**Acceptance Criteria:**
- Raw pipeline results are stored in MongoDB
- Complete extraction payloads are retrievable
- Historical extractions can be compared
- Data model is flexible for future enhancements

**Notes:**
- MongoDB allows schema flexibility for varying extraction formats
- Consider indexing by document_id and scan_job_id for performance
- Document collection schema in README

---

### 7. Persist Topology in Neo4j

**Status:** ⏳ NOT STARTED

**Description:** Store equipment relationships and topology graph.

**Tasks:**
- [ ] Create Neo4jClient wrapper in backend/app/database/neo4j.py
- [ ] Create TopologyRepository with methods:
  - [ ] create_equipment_node(tag, label, equipment_type, project_id) -> Node
  - [ ] create_connection(source_tag, target_tag, connection_type, flow_direction) -> Relationship
  - [ ] get_equipment_node(tag) -> Node
  - [ ] find_downstream_equipment(tag) -> List[Node]
  - [ ] find_upstream_equipment(tag) -> List[Node]
  - [ ] find_connected_equipment(tag) -> List[Node]
  - Status: ⏳
- [ ] Define Neo4j graph schema:
  - [ ] Node labels: Equipment, Project, Document
  - [ ] Equipment properties: tag, label, type, project_id
  - [ ] Relationships:
    - [ ] CONNECTED_TO (pipe connections)
    - [ ] FLOWS_TO (flow direction)
    - [ ] PART_OF (equipment -> project)
    - [ ] EXTRACTED_FROM (equipment -> document)
  - Status: ⏳
- [ ] Modify process_uploaded_pid() to populate Neo4j:
  - [ ] After equipment extraction, create Equipment nodes
  - [ ] Use graph_builder to infer connections
  - [ ] Create CONNECTED_TO and FLOWS_TO relationships
  - [ ] Link to project and document
  - Status: ⏳
- [ ] Add GET /api/projects/{project_id}/topology endpoint:
  - [ ] Return graph structure (nodes and edges)
  - [ ] Response: {"nodes": [{"id": tag, "label": string, "type": string}], "edges": [{"source": tag, "target": tag, "type": string}]}
  - Status: ⏳
- [ ] Add GET /api/projects/{project_id}/equipment/{tag}/downstream endpoint:
  - [ ] Return all equipment downstream from given tag
  - [ ] Status: ⏳
- [ ] Add GET /api/projects/{project_id}/equipment/{tag}/upstream endpoint:
  - [ ] Return all equipment upstream from given tag
  - [ ] Status: ⏳
- [ ] Add GET /api/projects/{project_id}/equipment/{tag}/connected endpoint:
  - [ ] Return all directly connected equipment
  - [ ] Status: ⏳
- [ ] Implement graph queries for:
  - [ ] All paths between two equipment items
  - [ ] Equipment isolation (disconnected islands)
  - [ ] Flow paths and loop detection
  - Status: ⏳

**Acceptance Criteria:**
- Topology graph is persisted and queryable
- Equipment relationships are accurately stored
- Graph queries return correct results
- Topology can be retrieved and visualized

**Notes:**
- Consider storing flow direction and connection type
- Add graph visualization support in Phase 3
- Document Neo4j schema and query patterns

---

### 8. API Changes for Persistent Project and Document Workflow

**Status:** ⏳ NOT STARTED

**Description:** Update API to support project-scoped document workflow.

**New Endpoints:**

**Projects:**
- [ ] POST /api/projects
  - Request: {"name": string, "description": string}
  - Response: {"id": uuid, "name": string, "description": string, "status": string, "created_at": timestamp}
  - Status: ⏳
- [ ] GET /api/projects
  - Response: {"projects": [...]}
  - Status: ⏳
- [ ] GET /api/projects/{project_id}
  - Response: {"id": uuid, "name": string, "documents": [...], "equipment_count": int, "created_at": timestamp}
  - Status: ⏳
- [ ] PUT /api/projects/{project_id}
  - Request: {"name": string, "description": string, "status": string}
  - Response: Updated project object
  - Status: ⏳

**Documents:**
- [ ] POST /api/projects/{project_id}/documents (upload)
  - Request: multipart/form-data with file
  - Response: {"id": uuid, "filename": string, "status": string, "created_at": timestamp}
  - Status: ⏳
- [ ] GET /api/projects/{project_id}/documents
  - Response: {"documents": [...]}
  - Status: ⏳
- [ ] GET /api/projects/{project_id}/documents/{document_id}
  - Response: {"id": uuid, "filename": string, "status": string, "file_size": int, "uploaded_at": timestamp}
  - Status: ⏳

**Scanning:**
- [ ] POST /api/projects/{project_id}/documents/{document_id}/scan
  - Request: (body optional, file already uploaded)
  - Response: {"job_id": uuid, "status": string, "message": string}
  - Status: ⏳
- [ ] GET /api/projects/{project_id}/documents/{document_id}/scan-status
  - Response: {"job_id": uuid, "status": string, "progress": int, "results": {...}}
  - Status: ⏳

**Equipment:**
- [ ] GET /api/projects/{project_id}/equipment
  - Response: {"equipment": [{"id": uuid, "tag": string, "type": string, "confidence": float}]}
  - Status: ⏳
- [ ] GET /api/projects/{project_id}/documents/{document_id}/equipment
  - Response: {"equipment": [...]}
  - Status: ⏳

**BOM:**
- [ ] GET /api/projects/{project_id}/bom
  - Response: {"materials": [...], "total_items": int, "total_cost": float}
  - Status: ⏳
- [ ] GET /api/projects/{project_id}/documents/{document_id}/bom
  - Response: {"materials": [...], "total_items": int, "total_cost": float}
  - Status: ⏳

**Tasks:**
- [ ] Update routes.py with all new endpoints
- [ ] Implement project context propagation through all routes
- [ ] Add proper authorization checks (if multi-user)
- [ ] Update frontend to use new project-scoped endpoints
- [ ] Add pagination for list endpoints
- [ ] Add query filters (by status, date range, etc.)
- [ ] Document all endpoints in API schema/OpenAPI

**Acceptance Criteria:**
- All API endpoints support project-scoped workflow
- Documents are associated with projects
- Equipment and BOM are queryable by project and document
- API is backward compatible or has clear migration path
- All endpoints have proper error handling

---

### 9. Phase 2 Completion Checklist

**Status:** ⏳ NOT STARTED

**Checklist:**
- [ ] Database schema is defined and documented
- [ ] Migrations are created and tested
- [ ] Projects can be created and listed
- [ ] Documents can be uploaded and associated with projects
- [ ] Scan jobs are persisted and queryable
- [ ] Extracted equipment is stored in PostgreSQL
- [ ] BOM materials are stored in PostgreSQL
- [ ] Raw extraction artifacts are stored in MongoDB
- [ ] Topology is stored in Neo4j
- [ ] All Phase 2 API endpoints are implemented
- [ ] Project-scoped queries work correctly
- [ ] Data relationships are maintained correctly
- [ ] No data loss occurs during processing
- [ ] Historical data is retrievable
- [ ] Frontend updated to use new API structure
- [ ] Integration tests pass for upload → store → retrieve flow

**Acceptance Criteria:**
- A project has uploaded documents
- Documents have extracted equipment and BOM
- All data is persisted and retrievable
- Full workflow is database-backed

---

## Priority Implementation Order

### Phase 1 Priority Sequence
1. Dependency and import validation
2. App startup and configuration
3. Service dependency validation
4. API smoke tests
5. Frontend compatibility
6. Phase 1 deliverable validation

### Phase 2 Priority Sequence
1. Define data model
2. Create migrations
3. Persist uploaded files
4. Persist scan jobs
5. Persist equipment and BOM
6. Persist raw artifacts
7. Persist topology
8. Update API endpoints
9. Phase 2 deliverable validation

---

## Development Notes

### Local Development Setup
```bash
# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt
pip install -r backend/requirements-db.txt
pip install -r ai_pipeline/requirements.txt

# Start services
docker compose up -d

# Run migrations (Phase 2)
alembic upgrade head

# Start backend
cd backend
uvicorn app.main:app --reload

# Open frontend
open frontend/bom-generator.html
```

### Testing Endpoints
```bash
# Health check
curl http://localhost:8000/api/health

# Upload file
curl -X POST "http://localhost:8000/api/upload" -F "file=@sample.pdf"

# Scan file
curl -X POST "http://localhost:8000/api/scan" -F "file=@sample.pdf"

# Get materials
curl http://localhost:8000/api/materials

# Get job status
curl http://localhost:8000/api/jobs/{job_id}
```

### Debugging
- Check backend logs: `docker compose logs backend`
- Check AI worker logs: `docker compose logs worker`
- Check database connections: verify credentials in .env
- Monitor API requests: use browser Network tab or curl -v
- Inspect uploaded files: `ls backend/uploads/`

---

## Document History

- **2026-10-01:** Initial Phase 1 and 2 roadmap created
- **Status:** Phase 1 NOT STARTED, Phase 2 NOT STARTED

---

## Next Steps

After Phase 2 completion, proceed to:
- **Phase 3:** Add async processing queue (Redis + Celery)
- **Phase 4:** Improve engineering document extraction quality
- **Phase 5:** Implement topology graph visualization
- **Phase 6:** Add user-facing review and analytics UI
- **Phase 7:** Production hardening and deployment
- **Phase 8:** BOM refinement and business logic

