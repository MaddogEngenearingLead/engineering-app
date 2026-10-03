from __future__ import annotations

import re
from pathlib import Path

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False


def extract_text_from_pdf(file_path: str) -> str:
    """Extract all text from a PDF file."""
    if not HAS_PDFPLUMBER:
        return ""

    try:
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return ""


def extract_tags_from_text(text: str) -> list[dict[str, object]]:
    """
    Extract equipment tags from text using regex patterns.
    Looks for common P&ID tag patterns like P-101, V-201, E-301, etc.
    """
    tags = []
    seen = set()

    # Common P&ID tag patterns
    patterns = [
        # Equipment prefix patterns: P (pump), V (valve), E (vessel), C (compressor), etc.
        (r"\b([A-Z])-?(\d{2,4})\b", "generic"),
        # Explicit patterns for common equipment
        (r"\bPUMP[\s-]*([A-Z]\d{2,4}|\d{3,4})\b", "pump"),
        (r"\bVALVE[\s-]*([A-Z]\d{2,4}|\d{3,4})\b", "valve"),
        (r"\bVESSEL[\s-]*([A-Z]\d{2,4}|\d{3,4})\b", "vessel"),
        (r"\bCOMPRESSOR[\s-]*([A-Z]\d{2,4}|\d{3,4})\b", "compressor"),
        (r"\bFLOWMETER[\s-]*([A-Z]\d{2,4}|\d{3,4})\b", "flowmeter"),
        (r"\bPRESSURE[\s-]*([A-Z]\d{2,4}|\d{3,4})\b", "sensor"),
        (r"\bTEMPERATURE[\s-]*([A-Z]\d{2,4}|\d{3,4})\b", "sensor"),
    ]

    for pattern, equipment_type in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            tag = match.group(0).upper().replace(" ", "-").replace("_", "-")
            if tag not in seen:
                seen.add(tag)
                tags.append({
                    "tag": tag,
                    "type": equipment_type,
                    "confidence": 0.75,
                    "source": "regex_extraction",
                })

    return tags


def infer_equipment_type(tag: str) -> str:
    """
    Infer equipment type from tag prefix.
    Common P&ID conventions:
    - P: Pump
    - V: Valve
    - E: Vessel/Equipment
    - C: Compressor
    - F: Flowmeter
    - T: Temperature sensor
    - PS: Pressure sensor
    """
    prefix = tag.split("-")[0].upper()

    type_map = {
        "P": "pump",
        "V": "valve",
        "E": "vessel",
        "C": "compressor",
        "F": "flowmeter",
        "T": "temperature_sensor",
        "PS": "pressure_sensor",
        "FL": "level_indicator",
        "PI": "pressure_indicator",
        "TI": "temperature_indicator",
    }

    return type_map.get(prefix, "unknown_equipment")


def generate_bom_from_tags(tags: list[dict[str, object]]) -> list[dict[str, object]]:
    """
    Generate a basic BOM (Bill of Materials) from extracted tags.
    Assigns default costs and quantities based on equipment type.
    """
    bom = []
    item_number = 1

    # Default unit costs by equipment type
    cost_map = {
        "pump": 2500.0,
        "valve": 350.0,
        "vessel": 5000.0,
        "compressor": 8000.0,
        "flowmeter": 1200.0,
        "temperature_sensor": 250.0,
        "pressure_sensor": 300.0,
        "level_indicator": 400.0,
        "pressure_indicator": 200.0,
        "temperature_indicator": 200.0,
        "unknown_equipment": 500.0,
    }

    for tag_info in tags:
        tag = tag_info["tag"]
        equipment_type = tag_info.get("type", infer_equipment_type(tag))
        unit_cost = cost_map.get(equipment_type, 500.0)
        quantity = 1  # Default quantity; could be enhanced with regex

        bom.append({
            "item_number": item_number,
            "tag_id": tag,
            "description": f"{equipment_type.replace('_', ' ').title()}",
            "type": equipment_type,
            "quantity": quantity,
            "unit": "ea",
            "supplier": "Extracted from P&ID",
            "unit_cost": unit_cost,
            "total_cost": unit_cost * quantity,
        })
        item_number += 1

    return bom
