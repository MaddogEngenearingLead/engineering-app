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
    Extract equipment tags from text using improved regex patterns.
    Handles multi-letter prefixes like TK-1, JFSP-1, MOV-001, etc.
    """
    tags = []
    seen = set()

    # Equipment tag patterns - ordered by specificity
    # These match real P&ID tag formats from your drawing
    patterns = [
        # Multi-letter equipment tags: TK-1, JFSP-1, JFLP-1, MOV-001, etc.
        # 2-5 letter prefix followed by optional dash and 1-4 digits
        (r"\b([A-Z]{2,5})\s*[-]?\s*(\d{1,4})\b", "equipment"),
        # Motor-operated valves: MOV-001, MOV F 002 (handles space-separated)
        # MOV can be followed by optional 'F' and numbers with or without dash
        (r"\bMOV\s*[F]?\s*[-]?(\d{3,4})\b", "valve"),
    ]

    # Exclude patterns - skip these even if they match (sheet/drawing references)
    exclude_patterns = [
        r"^M-\d{3}$",      # M-601, M-602 (drawing references)
        r"^MD\d{3}$",      # MD601, MD602 (drawing identifiers)
        r"^DRG$",          # Drawing abbreviation
    ]

    for pattern, tag_type in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            # Reconstruct full tag from the groups
            if tag_type == "valve" and "MOV" in match.group(0):
                # For MOV valves, use MOV + number
                full_tag = f"MOV-{match.group(1)}"
            else:
                # For other equipment, combine prefix + number with dash
                prefix = match.group(1).upper()
                number = match.group(2)
                full_tag = f"{prefix}-{number}"
            
            # Skip excluded patterns
            if any(re.match(excl, full_tag) for excl in exclude_patterns):
                continue

            if full_tag not in seen:
                seen.add(full_tag)
                
                # Infer equipment type from prefix
                prefix = full_tag.split("-")[0]
                equipment_type = infer_equipment_type(prefix)
                
                tags.append({
                    "tag": full_tag,
                    "type": equipment_type,
                    "confidence": 0.85,
                    "source": "regex_extraction",
                    "prefix": prefix,
                })

    return tags


def infer_equipment_type(prefix: str) -> str:
    """
    Infer equipment type from tag prefix.
    Maps real P&ID prefixes to equipment types.
    """
    prefix = prefix.upper()

    type_map = {
        # Your drawing's equipment
        "TK": "tank",
        "JFSP": "pump",
        "JFLP": "pump",
        "MOV": "valve",
        
        # Common instruments
        "PS": "pressure_sensor",
        "PI": "pressure_indicator",
        "TI": "temperature_indicator",
        "FI": "flow_indicator",
        "LI": "level_indicator",
        
        # Vents and drains
        "PV": "pressure_vent",
        "EV": "emergency_vent",
        "LPD": "low_point_drain",
        "HPV": "high_point_vent",
        
        # Other equipment
        "FS": "filter_separator",
        "F": "filter",
        "S": "strainer",
        "C": "compressor",
        "P": "pump",
        "V": "valve",
        "E": "vessel",
    }

    return type_map.get(prefix, "equipment")


def generate_bom_from_tags(tags: list[dict[str, object]]) -> list[dict[str, object]]:
    """
    Generate a BOM (Bill of Materials) from extracted tags.
    No pricing - focus on equipment identification and scope.
    """
    bom = []
    item_number = 1

    # Description map for equipment types
    description_map = {
        "tank": "Storage Tank",
        "pump": "Centrifugal Pump",
        "valve": "Motor-Operated Valve",
        "pressure_sensor": "Pressure Sensor",
        "pressure_indicator": "Pressure Indicator",
        "temperature_indicator": "Temperature Indicator",
        "flow_indicator": "Flow Indicator",
        "level_indicator": "Level Indicator",
        "pressure_vent": "Pressure Vent",
        "emergency_vent": "Emergency Vent",
        "low_point_drain": "Low Point Drain",
        "high_point_vent": "High Point Vent",
        "filter_separator": "Filter/Separator",
        "filter": "Filter",
        "strainer": "Strainer",
        "equipment": "Equipment",
    }

    for tag_info in tags:
        tag = tag_info["tag"]
        equipment_type = tag_info.get("type", "equipment")
        description = description_map.get(equipment_type, "Equipment")
        quantity = 1  # Default quantity

        bom.append({
            "item_number": item_number,
            "tag_id": tag,
            "description": description,
            "type": equipment_type,
            "quantity": quantity,
            "unit": "ea",
            "confidence": tag_info.get("confidence", 0.85),
        })
        item_number += 1

    return bom
