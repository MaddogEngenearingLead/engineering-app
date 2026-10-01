from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse

from app.core.config import settings

router = APIRouter()


@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }


@router.post("/upload")
async def upload_pid(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="A file is required.")

    upload_path = settings.upload_path
    upload_path.mkdir(parents=True, exist_ok=True)

    file_ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    allowed_exts = {"pdf", "png", "jpg", "jpeg", "svg"}
    if file_ext not in allowed_exts:
        raise HTTPException(status_code=400, detail="Unsupported file type.")

    file_size = 0
    content = await file.read()
    file_size = len(content)

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if file_size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum allowed size of {settings.max_upload_size_mb} MB.",
        )

    saved_name = f"{file.filename}"
    save_location = upload_path / saved_name
    save_location.write_bytes(content)

    return {
        "message": "File uploaded successfully.",
        "filename": file.filename,
        "saved_path": str(save_location),
        "content_type": file.content_type,
        "size_bytes": file_size,
    }


@router.post("/scan")
async def scan_pid(file: UploadFile = File(...)) -> dict[str, Any]:
    upload_result = await upload_pid(file)

    return {
        "job_id": "job-pid-001",
        "status": "queued",
        "message": "P&ID scan job accepted and queued for AI processing.",
        "source_file": upload_result["saved_path"],
        "detected_assets": [
            {"tag": "P-101", "type": "pump", "count": 1},
            {"tag": "V-101", "type": "valve", "count": 2},
            {"tag": "E-101", "type": "vessel", "count": 1},
        ],
    }


@router.get("/materials")
def get_materials() -> dict[str, Any]:
    return {
        "materials": [
            {
                "item_number": 1,
                "tag_id": "P-101",
                "description": "Centrifugal pump",
                "type": "pump",
                "quantity": 1,
                "unit": "ea",
                "supplier": "Flowserve",
                "unit_cost": 3400.0,
                "total_cost": 3400.0,
            },
            {
                "item_number": 2,
                "tag_id": "V-101",
                "description": "Gate valve",
                "type": "valve",
                "quantity": 2,
                "unit": "ea",
                "supplier": "Cameron",
                "unit_cost": 950.0,
                "total_cost": 1900.0,
            },
            {
                "item_number": 3,
                "tag_id": "E-101",
                "description": "Process vessel",
                "type": "vessel",
                "quantity": 1,
                "unit": "ea",
                "supplier": "Eagle Tanks",
                "unit_cost": 12500.0,
                "total_cost": 12500.0,
            },
        ],
        "total_items": 3,
        "estimated_total_cost": 17800.0,
    }


@router.get("/jobs/{job_id}")
def get_job_status(job_id: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "status": "completed",
        "progress": 100,
        "message": "AI processing finished successfully.",
    }


@router.get("/projects")
def list_projects() -> dict[str, Any]:
    return {
        "projects": [
            {
                "id": "project-001",
                "name": "Main Process Line",
                "status": "active",
                "last_updated": "2026-09-30T00:00:00Z",
            },
            {
                "id": "project-002",
                "name": "Reactor Unit",
                "status": "queued",
                "last_updated": "2026-09-29T00:00:00Z",
            },
        ]
    }


@router.get("/")
def root() -> dict[str, str]:
    return {"message": "Engineering PID API is running."}


@router.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
