from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.services.pid_processing import process_uploaded_pid
from app.services.job_store import JOB_STORE

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
    allowed_exts = {"pdf", "png", "jpg", "jpeg", "svg", "gif"}
    if file_ext not in allowed_exts:
        raise HTTPException(status_code=400, detail="Unsupported file type.")

    content = await file.read()
    file_size = len(content)
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if file_size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum allowed size of {settings.max_upload_size_mb} MB.",
        )

    save_location = upload_path / file.filename
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
    file_path = upload_result["saved_path"]
    job_id = f"pid-job-{len(JOB_STORE._jobs) + 1:04d}"

    result = process_uploaded_pid(file_path)
    result["job_id"] = job_id
    JOB_STORE.add(job_id, result)

    return {
        "job_id": job_id,
        "status": "completed",
        "message": "Engineering document scan processed successfully.",
        "source_file": file_path,
        "detected_assets": result.get("detected_assets", []),
        "materials": result.get("materials", []),
        "total_items": result.get("total_items", 0),
        "estimated_total_cost": result.get("estimated_total_cost", 0.0),
        "page_count": result.get("pipeline_output", {}).get("pages_processed", 0),
    }


@router.get("/materials")
def get_materials() -> dict[str, Any]:
    latest_job = JOB_STORE.latest()
    if latest_job and latest_job.get("materials"):
        return {
            "materials": latest_job["materials"],
            "total_items": latest_job.get("total_items", len(latest_job["materials"])),
            "estimated_total_cost": latest_job.get("estimated_total_cost", 0.0),
        }

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
            }
        ],
        "total_items": 1,
        "estimated_total_cost": 3400.0,
    }


@router.get("/jobs/{job_id}")
def get_job_status(job_id: str) -> dict[str, Any]:
    job = JOB_STORE.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    return {
        "job_id": job_id,
        "status": job.get("status", "completed"),
        "progress": 100,
        "message": job.get("message", "Processing completed."),
        "source_file": job.get("source_file"),
    }


@router.get("/projects")
def list_projects() -> dict[str, Any]:
    return {
        "projects": [
            {"id": "project-001", "name": "Main Process Line", "status": "active"},
            {"id": "project-002", "name": "Reactor Unit", "status": "queued"},
        ]
    }


@router.get("/")
def root() -> dict[str, str]:
    return {"message": "Engineering PID API is running."}


@router.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
