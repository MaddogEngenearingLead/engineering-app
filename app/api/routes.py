from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse

from app.config import settings
from app.services.scope_bom import (
    EXPORT_FAILURE_MESSAGE,
    ScopeOverrideError,
    build_scoped_bom,
)

router = APIRouter(tags=["engineering"])
logger = logging.getLogger(__name__)


def sanitize_filename(filename: str) -> str:
    """Remove potentially dangerous characters from filename."""
    # Replace path separators and other dangerous chars
    dangerous_chars = ['/', '\\', '..', ':', '*', '?', '"', '<', '>', '|']
    sanitized = filename
    for char in dangerous_chars:
        sanitized = sanitized.replace(char, '_')
    return sanitized


def _parse_page_numbers(value: str, field_name: str) -> list[int]:
    if not value.strip():
        return []
    try:
        parsed = json.loads(value) if value.lstrip().startswith("[") else value.split(",")
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail=f"{field_name} must be a JSON array or comma-separated list.") from error
    if not isinstance(parsed, list):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a list of positive page numbers.")
    pages = []
    for page in parsed:
        if isinstance(page, bool):
            raise HTTPException(status_code=400, detail=f"{field_name} must contain positive integers.")
        try:
            number = int(page)
        except (TypeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=f"{field_name} must contain positive integers.") from error
        if number <= 0 or str(page).strip() != str(number):
            raise HTTPException(status_code=400, detail=f"{field_name} must contain positive integers.")
        if number not in pages:
            pages.append(number)
    return pages


def _parse_highlight_mapping(value: str) -> dict[str, str]:
    if not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail="highlight_mapping must be a JSON object.") from error
    if not isinstance(parsed, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in parsed.items()
    ):
        raise HTTPException(status_code=400, detail="highlight_mapping must map string keys to string values.")
    if any(item.lower() not in {"demo", "new", "future"} for item in parsed.values()):
        raise HTTPException(
            status_code=400,
            detail="highlight_mapping values must be demo, new, or future.",
        )
    return parsed


def _scan_failure(message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "job_id": None,
            "status": "failed",
            "message": message,
            "source_file": None,
            "file_id": None,
            "detected_assets": [],
            "materials": [],
            "total_items": 0,
            "extraction_method": "text_extraction",
            "extracted_text_length": 0,
            "scope_of_work": "",
            "review_notes": [],
            "page_classifications": [],
            "ambiguous_material_tags": [],
            "scope_check": None,
            "legend": None,
            "colour_analysis": None,
            "needs_clarification": False,
            "clarification_prompts": [],
            "bom_pdf": None,
            "export_status": "not_generated",
            "export_error": None,
        },
    )


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


@router.post("/scan")
async def scan_pid(
    file: UploadFile = File(...),
    scope_of_work: str = Form(default=""),
    review_notes: str = Form(default=""),
    demo_pages: str = Form(default=""),
    new_work_pages: str = Form(default=""),
    highlight_mapping: str = Form(default=""),
) -> dict[str, object]:
    """Scan a P&ID and build a scoped BOM, including clarification and export status."""
    try:
        parsed_demo_pages = _parse_page_numbers(demo_pages, "demo_pages")
        parsed_new_pages = _parse_page_numbers(new_work_pages, "new_work_pages")
        parsed_highlight_mapping = _parse_highlight_mapping(highlight_mapping)
    except HTTPException as error:
        return _scan_failure("Invalid scan parameters.", error.status_code)
    notes_list = [note.strip() for note in review_notes.split(",") if note.strip()]

    # First upload the file
    try:
        upload_result = await upload_pid(file)
    except HTTPException as error:
        return _scan_failure("The uploaded file was rejected by validation.", error.status_code)
    file_id = upload_result["file_id"]
    file_path = upload_result["saved_path"]
    source_file = upload_result["original_filename"]
    job_id = f"job-{file_id}"

    try:
        result = build_scoped_bom(
            pdf_path=file_path,
            scope_of_work=scope_of_work,
            demo_pages=parsed_demo_pages,
            new_work_pages=parsed_new_pages,
            highlight_mapping=parsed_highlight_mapping,
            review_notes=notes_list,
            job_id=job_id,
            source_file=source_file,
        )
    except ScopeOverrideError as error:
        return _scan_failure(str(error), 400)
    except Exception:
        logger.exception("Scoped BOM scan failed.")
        return _scan_failure("P&ID scan could not be completed due to a server error.", 500)
    needs_clarification = result["needs_clarification"]
    status = "failed" if result["export_status"] == "failed" else (
        "needs_clarification" if needs_clarification else "completed"
    )
    return {
        "job_id": job_id,
        "status": status,
        "message": (
            f"P&ID scan completed; {EXPORT_FAILURE_MESSAGE}"
            if result["export_status"] == "failed" else
            "P&ID scan completed; review the clarification prompts."
            if needs_clarification else
            "P&ID scan completed successfully."
        ),
        "source_file": source_file,
        "file_id": file_id,
        "detected_assets": result["detected_assets"],
        "materials": result["materials"],
        "total_items": len(result["materials"]),
        "extraction_method": "text_extraction",
        "extracted_text_length": result["extracted_text_length"],
        "scope_of_work": scope_of_work,
        "review_notes": notes_list,
        "page_classifications": result["page_classifications"],
        "ambiguous_material_tags": result["ambiguous_material_tags"],
        "scope_check": result["scope_check"],
        "legend": result["legend"],
        "colour_analysis": result["colour_analysis"],
        "needs_clarification": needs_clarification,
        "clarification_prompts": result["clarification_prompts"],
        "bom_pdf": result["bom_pdf"],
        "export_status": result["export_status"],
        "export_error": result["export_error"] or None,
    }


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
