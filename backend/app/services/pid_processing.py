from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_pipeline.universal_processor import process_pid_file_universal


def process_uploaded_pid(file_path: str) -> dict[str, Any]:
    """Bridge between FastAPI upload route and the document AI pipeline."""
    result = process_pid_file_universal(file_path)

    equipment = result.get("equipment", [])
    materials = []
    for index, item in enumerate(equipment, start=1):
        tag = item.get("tag", f"AUTO-{index}")
        description = item.get("label") or item.get("source_text") or item.get("type", "Detected equipment")
        item_type = item.get("type", "equipment")
        confidence = float(item.get("confidence", 0.0))
        unit_cost = round(confidence * 1000, 2)

        materials.append(
            {
                "item_number": index,
                "tag_id": tag,
                "description": description,
                "type": item_type,
                "quantity": 1,
                "unit": "ea",
                "supplier": "Auto-generated",
                "unit_cost": unit_cost,
                "total_cost": unit_cost,
            }
        )

    bom_items = result.get("bom_items", [])
    if bom_items:
        materials = []
        for index, item in enumerate(bom_items, start=1):
            tag = item.get("tag", f"AUTO-{index}")
            description = item.get("description", "Equipment")
            unit_cost = round(float(item.get("quantity", 1)) * 200.0, 2)
            materials.append(
                {
                    "item_number": index,
                    "tag_id": tag,
                    "description": description,
                    "type": item.get("type", "equipment"),
                    "quantity": int(item.get("quantity", 1)),
                    "unit": "ea",
                    "supplier": "Auto-generated",
                    "unit_cost": unit_cost,
                    "total_cost": unit_cost,
                }
            )

    return {
        "job_id": "job-pid-generated",
        "status": "completed",
        "message": "Engineering document scan completed.",
        "source_file": file_path,
        "detected_assets": [
            {
                "tag": item.get("tag", f"AUTO-{idx + 1}"),
                "type": item.get("type", "equipment"),
                "count": 1,
                "confidence": item.get("confidence", 0.0),
            }
            for idx, item in enumerate(equipment)
        ],
        "materials": materials,
        "total_items": len(materials),
        "estimated_total_cost": round(sum(item["total_cost"] for item in materials), 2),
        "pipeline_output": result,
    }
