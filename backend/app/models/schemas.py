from __future__ import annotations

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    message: str
    filename: str
    saved_path: str
    content_type: str | None = None
    size_bytes: int


class MaterialItem(BaseModel):
    item_number: int
    tag_id: str
    description: str
    type: str
    quantity: int
    unit: str
    supplier: str
    unit_cost: float
    total_cost: float


class MaterialResponse(BaseModel):
    materials: list[MaterialItem]
    total_items: int
    estimated_total_cost: float


class ProcessJob(BaseModel):
    job_id: str
    status: str
    message: str
    source_file: str
    detected_assets: list[dict[str, str | int]]


class ProjectSummary(BaseModel):
    id: str
    name: str
    status: str
    last_updated: str
