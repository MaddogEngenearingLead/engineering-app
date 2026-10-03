from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from fastapi import APIRouter, File, UploadFile, HTTPException, Form

from app.config import settings
from app.services.scope_bom import build_scoped_bom

router = APIRouter(tags=["engineering"])


def sanitize_filename(filename: str) -> str:
    """Remove potentially dangerous characters from filename."""
    # Replace path separators and other dangerous chars
    dangerous_chars = ['/', '\\', '..', ':', '*', '?', '"', '<', '>', '|']
    sanitized = filename
    for char in dangerous_chars:
        sanitized = sanitized.replace(char, '_')
    return sanitized


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name, "environment": settings.environment}


@router.get("/pipeline")
def get_pipeline_summary() -> dict[str, object]:
    return {
        "asset_count": 0,
        "status": "initialized",
        "message": "Pipeline monitoring dashboard is ready for configuration.",
    }


@router.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Engineering App API is running"}


@router.post("/upload")
async def upload_pid(file: UploadFile = File(...)) -> dict[str, object]:
    """Upload a P&ID file (PDF or image)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="A file is required.")

    # Validate file type
    file_ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    allowed_exts = {"pdf", "png", "jpg", "jpeg", "svg", "gif"}
    if file_ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: .{file_ext}. Allowed types: {', '.join(allowed_exts)}",
        )

    # Create upload directory if it doesn't exist
    upload_path = Path(settings.upload_dir)
    upload_path.mkdir(parents=True, exist_ok=True)

    # Check file size
    content = await file.read()
    file_size = len(content)
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if file_size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum allowed size of {settings.max_upload_size_mb} MB.",
        )

    # Generate unique filename with sanitization
    file_id = str(uuid.uuid4())[:8]
    sanitized_name = sanitize_filename(file.filename)
    unique_filename = f"{file_id}_{sanitized_name}"
    file_path = upload_path / unique_filename

    # Save file
    file_path.write_bytes(content)

    return {
        "status": "success",
        "message": "File uploaded successfully.",
        "file_id": file_id,
        "original_filename": file.filename,
        "saved_filename": unique_filename,
        "saved_path": str(file_path),
        "content_type": file.content_type,
        "size_bytes": file_size,
    }


def _parse_pages(value: str, name: str) -> list[int] | None:
    """Parse '2,3' (or JSON list) into a list of page numbers."""
    if not value or not value.strip():
        return None
    try:
        return [int(p) for p in re.split(r"[,\s]+", value.strip().strip("[]")) if p]
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{name} must be a comma-separated list of page numbers.")


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
    """
    Scan a P&ID and build a scope-aware BOM.

    Returns {"status": "completed", ...} or {"status": "needs_clarification", "questions": [...]}.
    Resubmit with demo_pages / new_work_pages / highlight_mapping (JSON) / legend_page / key_page
    to override any auto-detection.
    """
    mapping = None
    if highlight_mapping.strip():
        try:
            mapping = json.loads(highlight_mapping)
            if not isinstance(mapping, dict):
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=400, detail="highlight_mapping must be a JSON object.")

    upload_result = await upload_pid(file)
    file_id = upload_result["file_id"]
    job_id = f"job-{file_id}"
    notes_list = [note.strip() for note in review_notes.split(",") if note.strip()]

    result = build_scoped_bom(
        upload_result["saved_path"],
        scope_text=scope_of_work or None,
        demo_pages=_parse_pages(demo_pages, "demo_pages"),
        new_work_pages=_parse_pages(new_work_pages, "new_work_pages"),
        highlight_mapping=mapping,
        legend_page=legend_page,
        key_page=key_page,
        review_notes=notes_list,
        job_id=job_id,
        source_file=upload_result["original_filename"],
    )
    result.update({
        "job_id": job_id,
        "file_id": file_id,
        "source_file": upload_result["original_filename"],
    })
    if result["status"] == "completed":
        result.update({
            "total_items": len(result["materials"]),
            "scope_of_work": scope_of_work,
            "review_notes": notes_list,
        })
    return result


@router.get("/materials")
def get_materials() -> dict[str, object]:
    """Get the most recent BOM materials (placeholder sample data)."""
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


@router.get("/jobs/{job_id}")
def get_job_status(job_id: str) -> dict[str, object]:
    """Get the status of a scan job."""
    return {
        "job_id": job_id,
        "status": "completed",
        "progress": 100,
        "message": "Scan processing completed successfully.",
        "source_file": "sample.pdf",
    }
