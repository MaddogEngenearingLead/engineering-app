from __future__ import annotations

import uuid
from pathlib import Path
from fastapi import APIRouter, File, UploadFile, HTTPException

from app.config import settings
from app.services.pid_extraction import extract_text_from_pdf, extract_tags_from_text, generate_bom_from_tags
from app.services.bom_export import export_bom_to_json, export_bom_to_csv, export_bom_to_html

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


@router.post("/scan")
async def scan_pid(file: UploadFile = File(...)) -> dict[str, object]:
    """Scan a P&ID file and extract equipment/BOM data using text extraction."""
    # First upload the file
    upload_result = await upload_pid(file)
    file_id = upload_result["file_id"]
    file_path = upload_result["saved_path"]
    source_file = upload_result["original_filename"]
    job_id = f"job-{file_id}"

    # Extract text from PDF
    extracted_text = extract_text_from_pdf(file_path)

    # Extract tags from text
    detected_assets = extract_tags_from_text(extracted_text)

    # If no tags were found, return a helpful message
    if not detected_assets:
        return {
            "job_id": job_id,
            "status": "completed",
            "message": "P&ID scan completed. No equipment tags detected with current extraction methods.",
            "source_file": source_file,
            "file_id": file_id,
            "detected_assets": [],
            "materials": [],
            "total_items": 0,
            "extraction_method": "text_extraction",
            "note": "Consider using image-based OCR or manual tag entry for better results.",
            "bom_exports": {},
        }

    # Generate BOM from extracted tags (no pricing)
    materials = generate_bom_from_tags(detected_assets)

    # Export BOM to all formats
    bom_exports = {}
    try:
        bom_exports["json"] = export_bom_to_json(job_id, materials)
        bom_exports["csv"] = export_bom_to_csv(job_id, materials)
        bom_exports["html"] = export_bom_to_html(job_id, source_file, materials)
    except Exception as e:
        # Log error but don't fail the scan
        print(f"Warning: BOM export failed: {e}")

    return {
        "job_id": job_id,
        "status": "completed",
        "message": "P&ID scan completed successfully.",
        "source_file": source_file,
        "file_id": file_id,
        "detected_assets": detected_assets,
        "materials": materials,
        "total_items": len(materials),
        "extraction_method": "text_extraction",
        "extracted_text_length": len(extracted_text),
        "bom_exports": bom_exports,
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
