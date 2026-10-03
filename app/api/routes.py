from __future__ import annotations

import uuid
from pathlib import Path
from fastapi import APIRouter, File, UploadFile, HTTPException

from app.config import settings
from app.services.pid_extraction import extract_text_from_pdf, extract_tags_from_text, generate_bom_from_tags

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
    """Scan a P&ID file and extract equipment/BOM data using OCR and text extraction."""
    # First upload the file
    upload_result = await upload_pid(file)
    file_id = upload_result["file_id"]
    file_path = upload_result["saved_path"]

    # Extract text from PDF
    extracted_text = extract_text_from_pdf(file_path)

    # Extract tags from text
    detected_assets = extract_tags_from_text(extracted_text)

    # If no tags were found, return a helpful message
    if not detected_assets:
        return {
            "job_id": f"job-{file_id}",
            "status": "completed",
            "message": "P&ID scan completed. No equipment tags detected with current extraction methods.",
            "source_file": upload_result["original_filename"],
            "file_id": file_id,
            "detected_assets": [],
            "materials": [],
            "total_items": 0,
            "estimated_total_cost": 0.0,
            "extraction_method": "text_extraction",
            "note": "Consider using image-based OCR or manual tag entry for better results.",
        }

    # Generate BOM from extracted tags
    materials = generate_bom_from_tags(detected_assets)

    # Calculate total cost
    total_cost = sum(item["total_cost"] for item in materials)

    return {
        "job_id": f"job-{file_id}",
        "status": "completed",
        "message": "P&ID scan completed successfully.",
        "source_file": upload_result["original_filename"],
        "file_id": file_id,
        "detected_assets": detected_assets,
        "materials": materials,
        "total_items": len(materials),
        "estimated_total_cost": total_cost,
        "extraction_method": "text_extraction",
        "extracted_text_length": len(extracted_text),
    }


@router.get("/materials")
def get_materials() -> dict[str, object]:
    """Get the most recent BOM materials."""
    return {
        "materials": [
            {
                "item_number": 1,
                "tag_id": "P-101",
                "description": "Centrifugal Pump",
                "type": "pump",
                "quantity": 1,
                "unit": "ea",
                "supplier": "Flowserve",
                "unit_cost": 2500.0,
                "total_cost": 2500.0,
            },
            {
                "item_number": 2,
                "tag_id": "V-201",
                "description": "Gate Valve",
                "type": "valve",
                "quantity": 2,
                "unit": "ea",
                "supplier": "Emerson",
                "unit_cost": 350.0,
                "total_cost": 700.0,
            },
            {
                "item_number": 3,
                "tag_id": "E-301",
                "description": "Pressure Vessel",
                "type": "vessel",
                "quantity": 1,
                "unit": "ea",
                "supplier": "ASME Certified",
                "unit_cost": 5000.0,
                "total_cost": 5000.0,
            },
        ],
        "total_items": 3,
        "estimated_total_cost": 8200.0,
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
