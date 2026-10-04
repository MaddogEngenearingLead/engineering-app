from __future__ import annotations

import json
import re
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, UploadFile, HTTPException, Form

from app.config import settings
from app.job_manager import JobManager
from app.file_detector import FileDetector
from app.services.scope_bom import build_scoped_bom

router = APIRouter(tags=["engineering"])

# Initialize job manager
job_manager = JobManager(settings.upload_dir)


def sanitize_filename(filename: str) -> str:
    """Remove potentially dangerous characters from filename."""
    dangerous_chars = ["/", "\\", "..", ":", "*", "?", '"', "<", ">", "|"]
    sanitized = filename
    for char in dangerous_chars:
        sanitized = sanitized.replace(char, "_")
    return sanitized


# ============================================================================
# Health & Info Endpoints
# ============================================================================


@router.get("/health")
def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": settings.app_name, "environment": settings.environment}


@router.get("/pipeline")
def get_pipeline_summary() -> dict[str, object]:
    """Get pipeline summary."""
    return {
        "asset_count": 0,
        "status": "initialized",
        "message": "Pipeline monitoring dashboard is ready for configuration.",
    }


@router.get("/")
def read_root() -> dict[str, str]:
    """Root endpoint."""
    return {"message": "Engineering App API is running"}


# ============================================================================
# Job Management Endpoints
# ============================================================================


@router.post("/jobs")
def create_job(job_number: str = Form(...)) -> dict[str, object]:
    """Create a new job with the given job number.

    Creates folder structure:
    - backend/uploads/JOB-XXXX/pid/
    - backend/uploads/JOB-XXXX/scope/
    - backend/uploads/JOB-XXXX/bom_exports/
    """
    if not job_number or not job_number.strip():
        raise HTTPException(status_code=400, detail="Job number is required.")

    job_number = job_number.strip()

    try:
        job_dir, pid_dir, scope_dir, metadata = job_manager.get_or_create_job(job_number)
        return {
            "status": "success",
            "message": f"Job {job_number} created/initialized.",
            "job_number": job_number,
            "metadata": metadata,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating job: {str(e)}")


@router.get("/jobs")
def list_jobs() -> dict[str, object]:
    """List all existing jobs."""
    jobs = job_manager.list_jobs()
    return {
        "status": "success",
        "total_jobs": len(jobs),
        "jobs": jobs,
    }


@router.get("/jobs/{job_number}")
def get_job_info(job_number: str) -> dict[str, object]:
    """Get detailed information about a specific job."""
    info = job_manager.get_job_info(job_number)
    if info["status"] == "not_found":
        raise HTTPException(status_code=404, detail=f"Job {job_number} not found.")
    return info


# ============================================================================
# File Upload Endpoints (Job-Scoped)
# ============================================================================


@router.post("/jobs/{job_number}/upload-pid")
async def upload_pid_for_job(
    job_number: str,
    file: UploadFile = File(...),
) -> dict[str, object]:
    """Upload a P&ID file for a specific job.

    Saves to: backend/uploads/JOB-XXXX/pid/
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="A file is required.")

    file_ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    allowed_exts = {"pdf", "png", "jpg", "jpeg", "svg", "gif", "bmp", "tiff", "tif"}
    if file_ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: .{file_ext}. Allowed: {', '.join(sorted(allowed_exts))}",
        )

    content = await file.read()
    file_size = len(content)
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if file_size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {settings.max_upload_size_mb} MB limit.",
        )

    try:
        file_path = job_manager.save_pid_file(job_number, file.filename, content)
        return {
            "status": "success",
            "message": "P&ID uploaded successfully.",
            "job_number": job_number,
            "filename": file.filename,
            "saved_path": str(file_path),
            "size_bytes": file_size,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading P&ID: {str(e)}")


@router.post("/jobs/{job_number}/upload-scope")
async def upload_scope_for_job(
    job_number: str,
    file: UploadFile = File(...),
) -> dict[str, object]:
    """Upload a scope-of-work file for a specific job.

    Saves to: backend/uploads/JOB-XXXX/scope/
    Supports any text-readable format: TXT, MD, DOCX, PDF, JSON, CSV, etc.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="A file is required.")

    content = await file.read()
    file_size = len(content)
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if file_size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {settings.max_upload_size_mb} MB limit.",
        )

    try:
        file_path = job_manager.save_scope_file(job_number, file.filename, content)
        return {
            "status": "success",
            "message": "Scope file uploaded successfully.",
            "job_number": job_number,
            "filename": file.filename,
            "saved_path": str(file_path),
            "size_bytes": file_size,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading scope file: {str(e)}")


# ============================================================================
# BOM Generation Endpoints (Job-Scoped)
# ============================================================================


def _parse_pages(value: str, name: str) -> list[int] | None:
    """Parse page numbers from comma-separated or JSON-like list."""
    if not value or not value.strip():
        return None
    try:
        return [int(p) for p in re.split(r"[,\s]+", value.strip().strip("[]")) if p]
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{name} must be comma-separated page numbers.")


@router.post("/scan")
async def scan_pid(
    file: UploadFile = File(...),
    scope_of_work: str = Form(default=""),
    review_notes: str = Form(default=""),
    legend_page: int | None = Form(default=None),
    key_page: int | None = Form(default=None),
    demo_pages: str = Form(default=""),
    new_work_pages: str = Form(default=""),
    highlight_mapping: str = Form(default=""),
) -> dict[str, object]:
    """Unified single-endpoint BOM scan for a PDF and scope text.

    This is the canonical unified scan endpoint intended to replace the older
    scope-bom pipeline paths.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="A file is required.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    mapping = None
    if highlight_mapping.strip():
        try:
            mapping = json.loads(highlight_mapping)
            if not isinstance(mapping, dict):
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=400, detail="highlight_mapping must be a JSON object.")

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = Path(tmpdir) / sanitize_filename(file.filename)
        pdf_path.write_bytes(content)

        notes_list = [note.strip() for note in review_notes.split(",") if note.strip()]
        result = build_scoped_bom(
            str(pdf_path),
            scope_text=scope_of_work.strip(),
            demo_pages=_parse_pages(demo_pages, "demo_pages"),
            new_work_pages=_parse_pages(new_work_pages, "new_work_pages"),
            highlight_mapping=mapping,
            legend_page=legend_page,
            key_page=key_page,
            review_notes=notes_list,
            job_id=f"JOB-{uuid.uuid4().hex[:8]}",
            source_file=pdf_path.name,
            output_dir=tmpdir,
        )

        if result.get("status") == "completed":
            result["scope_of_work"] = scope_of_work.strip()[:200]
            result["review_notes"] = notes_list
        return result


@router.post("/jobs/{job_number}/scan")
async def scan_job_pid(
    job_number: str,
    pid_filename: Optional[str] = Form(default=None),
    scope_filename: Optional[str] = Form(default=None),
    scope_of_work: str = Form(default=""),
    review_notes: str = Form(default=""),
    legend_page: int | None = Form(default=None),
    key_page: int | None = Form(default=None),
    demo_pages: str = Form(default=""),
    new_work_pages: str = Form(default=""),
    highlight_mapping: str = Form(default=""),
) -> dict[str, object]:
    """Scan a P&ID and generate BOM for a specific job.

    If pid_filename is provided, use that file.
    Otherwise, use the latest P&ID in the job's pid/ folder.

    If scope_filename is provided, use that file.
    Otherwise, if scope_of_work is provided, use that text.
    Otherwise, use the latest scope file in the job's scope/ folder.
    """
    # Get or create job
    try:
        job_dir, pid_dir, scope_dir, metadata = job_manager.get_or_create_job(job_number)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error initializing job: {str(e)}")

    # Resolve P&ID file
    if pid_filename:
        pid_path = pid_dir / pid_filename
        if not pid_path.exists():
            raise HTTPException(status_code=404, detail=f"P&ID file not found: {pid_filename}")
    else:
        pid_files = job_manager.get_pid_files(job_number)
        if not pid_files:
            raise HTTPException(status_code=404, detail=f"No P&ID files in job {job_number}.")
        pid_path = pid_files[0]

    # Resolve scope text
    if scope_filename:
        scope_path = scope_dir / scope_filename
        if not scope_path.exists():
            raise HTTPException(status_code=404, detail=f"Scope file not found: {scope_filename}")
        from app.file_detector import FileDetector
        detector = FileDetector()
        effective_scope = detector.extract_text_from_file(scope_path)
    elif scope_of_work:
        effective_scope = scope_of_work.strip()
    else:
        scope_files = job_manager.get_scope_files(job_number)
        if scope_files:
            from app.file_detector import FileDetector
            detector = FileDetector()
            effective_scope = detector.extract_text_from_file(scope_files[0])
        else:
            effective_scope = ""

    if not effective_scope:
        raise HTTPException(
            status_code=400,
            detail="No scope-of-work text provided. Please supply scope_of_work, scope_filename, or upload a scope file.",
        )

    # Parse highlight mapping
    mapping = None
    if highlight_mapping.strip():
        try:
            mapping = json.loads(highlight_mapping)
            if not isinstance(mapping, dict):
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=400, detail="highlight_mapping must be a JSON object.")

    # Generate BOM
    job_id = f"JOB-{job_number}"
    notes_list = [note.strip() for note in review_notes.split(",") if note.strip()]
    bom_export_dir = job_dir / "bom_exports"

    try:
        result = build_scoped_bom(
            str(pid_path),
            scope_text=effective_scope,
            demo_pages=_parse_pages(demo_pages, "demo_pages"),
            new_work_pages=_parse_pages(new_work_pages, "new_work_pages"),
            highlight_mapping=mapping,
            legend_page=legend_page,
            key_page=key_page,
            review_notes=notes_list,
            job_id=job_id,
            source_file=pid_path.name,
            output_dir=str(bom_export_dir),
        )
        result.update({
            "job_number": job_number,
            "pid_file": pid_path.name,
            "scope_file": scope_filename or "auto-detected",
        })
        if result["status"] == "completed":
            result.update({
                "total_items": len(result["materials"]),
                "scope_of_work": effective_scope[:200],
                "review_notes": notes_list,
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating BOM: {str(e)}")


# ============================================================================
# Legacy Endpoints (For Backward Compatibility)
# ============================================================================


@router.get("/materials")
def get_materials() -> dict[str, object]:
    """Get sample materials (legacy endpoint)."""
    return {
        "materials": [
            {
                "item_number": 1,
                "tag_id": "TK-1",
                "description": "Storage Tank",
                "type": "tank",
                "quantity": 1,
                "unit": "ea",
            },
            {
                "item_number": 2,
                "tag_id": "JFSP-1",
                "description": "Centrifugal Pump",
                "type": "pump",
                "quantity": 1,
                "unit": "ea",
            },
        ],
        "total_items": 2,
    }


@router.get("/jobs/{job_id}/status")
def get_job_status(job_id: str) -> dict[str, object]:
    """Get job status (legacy endpoint)."""
    return {
        "job_id": job_id,
        "status": "completed",
        "progress": 100,
        "message": "Scan processing completed successfully.",
    }
