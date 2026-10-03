from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter, File, UploadFile, HTTPException

from app.config import settings

router = APIRouter(tags=["engineering"])


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

    # Save file
    file_path = upload_path / file.filename
    file_path.write_bytes(content)

    return {
        "status": "success",
        "message": "File uploaded successfully.",
        "filename": file.filename,
        "saved_path": str(file_path),
        "content_type": file.content_type,
        "size_bytes": file_size,
    }


@router.post("/scan")
async def scan_pid(file: UploadFile = File(...)) -> dict[str, object]:
    """Scan a P&ID file and extract equipment/BOM data."""
    # First upload the file
    upload_result = await upload_pid(file)

    # Mock scan results for now
    job_id = f"job-{hash(file.filename) % 10000:04d}"

    return {
        "job_id": job_id,
        "status": "completed",
        "message": "P&ID scan completed successfully.",
        "source_file": upload_result["filename"],
        "detected_assets": [
            {"tag": "P-101", "type": "pump", "confidence": 0.95},
            {"tag": "V-201", "type": "valve", "confidence": 0.92},
            {"tag": "E-301", "type": "vessel", "confidence": 0.88},
        ],
        "materials": [
            {
                "item_number": 1,
                "tag_id": "P-101",
                "description": "Centrifugal Pump",
                "type": "pump",
                "quantity": 1,
                "unit": "ea",
                "supplier": "Auto-detected",
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
                "supplier": "Auto-detected",
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
                "supplier": "Auto-detected",
                "unit_cost": 5000.0,
                "total_cost": 5000.0,
            },
        ],
        "total_items": 3,
        "estimated_total_cost": 8200.0,
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
