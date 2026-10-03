from __future__ import annotations

import json
import uuid
from pathlib import Path
from fastapi import APIRouter, File, UploadFile, HTTPException, Form

from app.config import settings
from app.services.pid_extraction import extract_text_from_pdf, extract_tags_from_text, generate_bom_from_tags
from app.services.bom_export import export_bom_to_pdf
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


def parse_page_list(value: str, name: str) -> list[int]:
    """Parse '2,3' or '[2, 3]' into a list of 1-based page numbers."""
    value = value.strip()
    if not value:
        return []
    try:
        parsed = json.loads(value) if value.startswith("[") else [int(v) for v in value.split(",") if v.strip()]
        return [int(v) for v in parsed]
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail=f"{name} must be a list of page numbers, e.g. 2,3")


def parse_highlight_mapping(value: str) -> dict[str, str]:
    value = value.strip()
    if not value:
        return {}
    try:
        mapping = json.loads(value)
    except ValueError:
        raise HTTPException(status_code=422, detail="highlight_mapping must be a JSON object")
    if not isinstance(mapping, dict) or not all(isinstance(v, str) for v in mapping.values()):
        raise HTTPException(status_code=422, detail="highlight_mapping must map colour to meaning")
    return {str(k): v for k, v in mapping.items()}


@router.post("/scan")
async def scan_pid(
    file: UploadFile = File(...),
    scope_of_work: str = Form(default=""),
    review_notes: str = Form(default=""),
    demo_pages: str = Form(default=""),
    new_work_pages: str = Form(default=""),
    highlight_mapping: str = Form(default=""),
) -> dict[str, object]:
    """
    Scan a P&ID file and extract equipment/BOM data using text extraction.
    Generates a professional PDF report.
    
    Args:
        file: P&ID file (PDF or image)
        scope_of_work: Description of the scope of work for this project
        review_notes: Comma-separated list of items or notes requiring review
        demo_pages: Optional 1-based demo/pre-work page numbers (overrides auto-detection)
        new_work_pages: Optional 1-based new-work/post-work page numbers
        highlight_mapping: Optional JSON object mapping colour to meaning,
            e.g. {"[0,1,0]": "new_work", "[1,0,0]": "demo"}

    For PDFs, demo vs. new-work pages are detected by content comparison. If that is
    ambiguous the response has status "needs_clarification"; resubmit with
    demo_pages / new_work_pages.
    """
    demo_list = parse_page_list(demo_pages, "demo_pages")
    new_list = parse_page_list(new_work_pages, "new_work_pages")
    mapping = parse_highlight_mapping(highlight_mapping)
    # First upload the file
    upload_result = await upload_pid(file)
    file_id = upload_result["file_id"]
    file_path = upload_result["saved_path"]
    source_file = upload_result["original_filename"]
    job_id = f"job-{file_id}"

    notes_list = [note.strip() for note in review_notes.split(",") if note.strip()]

    if file_path.lower().endswith(".pdf"):
        try:
            scoped = build_scoped_bom(file_path, scope_of_work, demo_list, new_list, mapping)
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e))
        base = {"job_id": job_id, "source_file": source_file, "file_id": file_id}
        if scoped["status"] == "needs_clarification":
            return {**base, **scoped}
        materials = scoped["materials"]
        bom_pdf_path = None
        try:
            bom_pdf_path = export_bom_to_pdf(
                job_id=job_id,
                source_file=source_file,
                materials=materials,
                scope_of_work=scope_of_work,
                review_notes=notes_list,
                scope_report=scoped,
            )
        except Exception as e:
            print(f"Warning: BOM PDF export failed: {e}")
        return {
            **base,
            **scoped,
            "status": "completed",
            "message": "Scope-aware BOM generated.",
            "detected_assets": scoped["tags"],
            "total_items": len(materials),
            "extraction_method": "scope_aware_content_comparison",
            "scope_of_work": scope_of_work,
            "review_notes": notes_list,
            "bom_pdf": bom_pdf_path,
        }

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
            "bom_pdf": None,
        }

    # Generate BOM from extracted tags (no pricing)
    materials = generate_bom_from_tags(detected_assets)

    # Export BOM to PDF
    bom_pdf_path = None
    try:
        bom_pdf_path = export_bom_to_pdf(
            job_id=job_id,
            source_file=source_file,
            materials=materials,
            scope_of_work=scope_of_work,
            review_notes=notes_list,
        )
    except Exception as e:
        print(f"Warning: BOM PDF export failed: {e}")

    return {
        "job_id": job_id,
        "status": "completed",
        "message": "P&ID scan completed successfully. BOM PDF generated.",
        "source_file": source_file,
        "file_id": file_id,
        "detected_assets": detected_assets,
        "materials": materials,
        "total_items": len(materials),
        "extraction_method": "text_extraction",
        "extracted_text_length": len(extracted_text),
        "scope_of_work": scope_of_work,
        "review_notes": notes_list,
        "bom_pdf": bom_pdf_path,
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
