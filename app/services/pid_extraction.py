from __future__ import annotations

import re
from pathlib import Path

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False


# Allowlist of real P&ID equipment tag prefixes
VALID_PREFIXES = {
    # Tanks and vessels
    "TK", "E", "V",
    # Pumps (multi-letter only to avoid false positives)
    "JFSP", "JFLP", "C",
    # Valves (multi-letter)
    "MOV", "PRV", "TRV", "PV", "POV",
    # Vents and drains
    "EV", "HPV", "LPD",
    # Instrumentation
    "LI", "PI", "PS", "TI", "FI", "PE", "FE", "ME",
    "LS", "LSL", "LSH", "LSHH",
    # Other equipment
    "FS", "POSP",
}

# Denylist of false positives to explicitly exclude
DENYLIST_PREFIXES = {
    "MD", "CS", "CSO", "CN", "NO", "ON", "OIL", "ROOM", "RM", "FILL",
    "SS", "OSC", "PSIG", "PLC", "JY", "MFXX", "UL", "MP", "DPL", "GAL",
    "PG", "POT", "XXX", "GY", "NC",
}


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


def extract_words_with_coords(file_path: str) -> list[dict]:
    """Extract words with their coordinates for better tag matching."""
    if not HAS_PDFPLUMBER:
        return []

    try:
        words = []
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                page_words = page.extract_words()
                for word in page_words:
                    words.append({
                        "text": word["text"],
                        "page": page_num,
                        "x0": word["x0"],
                        "top": word["top"],
                        "x1": word["x1"],
                        "bottom": word["bottom"],
                    })
        return words
    except Exception as e:
        print(f"Error extracting words from PDF: {e}")
        return []


def extract_tags_from_text(text: str) -> list[dict[str, object]]:
    """
    Extract equipment tags from text using improved regex patterns.
    - Only matches known equipment prefixes (allowlist)
    - Matches within single lines only (no cross-line matches)
    - Zero-pads valve numbers for deduplication
    - Skips false positives (denylist)
    """
    tags = []
    seen = set()

    # Build a regex pattern from the allowlist
    # Sort by length descending so longer prefixes match first (e.g., JFSP before J)
    sorted_prefixes = sorted(VALID_PREFIXES, key=len, reverse=True)
    prefix_pattern = "|".join(re.escape(p) for p in sorted_prefixes)

    # Pattern: prefix (2-5 letters) + optional dash/spaces (same line only) + 1-4 digits
    # Use [ \t]* to match spaces/tabs on the same line only (not newlines)
    pattern = rf"\b({prefix_pattern})[ \t]*-?[ \t]*(\d{{1,4}})\b"

    matches = re.finditer(pattern, text, re.IGNORECASE)
    for match in matches:
        prefix = match.group(1).upper()
        number = match.group(2)

        # Skip if prefix is in denylist
        if prefix in DENYLIST_PREFIXES:
            continue

        # Zero-pad MOV and similar valve numbers to 3 digits for consistency
        if prefix == "MOV" and len(number) < 3:
            number = number.zfill(3)

        full_tag = f"{prefix}-{number}"

        if full_tag not in seen:
            seen.add(full_tag)

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
    Maps P&ID prefixes to equipment types.
    """
    prefix = prefix.upper()

    type_map = {
        # Your drawing's primary equipment
        "TK": "tank",
        "JFSP": "pump",
        "JFLP": "pump",
        "MOV": "valve",
        "POV": "pilot_operated_valve",

        # Vents and drains
        "EV": "emergency_vent",
        "PV": "pressure_vent",
        "HPV": "high_point_vent",
        "LPD": "low_point_drain",
        "PRV": "pressure_relief_valve",
        "TRV": "temperature_relief_valve",

        # Instrumentation
        "PS": "pressure_sensor",
        "PI": "pressure_indicator",
        "PE": "pressure_element",
        "TI": "temperature_indicator",
        "FI": "flow_indicator",
        "FE": "flow_element",
        "LI": "level_indicator",
        "LS": "level_switch",
        "LSL": "level_switch_low",
        "LSH": "level_switch_high",
        "LSHH": "level_switch_high_high",
        "ME": "measurement_element",

        # Other equipment
        "FS": "filter_separator",
        "POSP": "pump_outlet_shutoff_pressure",

        # Generic fallbacks
        "V": "valve",
        "E": "vessel",
        "C": "compressor",
    }

    return type_map.get(prefix, "equipment")


def generate_bom_from_tags(tags: list[dict[str, object]]) -> list[dict[str, object]]:
    """
    Generate a BOM (Bill of Materials) from extracted tags.
    No pricing — focus on equipment identification and scope.
    """
    bom = []
    item_number = 1

    description_map = {
        "tank": "Storage Tank",
        "pump": "Centrifugal Pump",
        "valve": "Motor-Operated Valve",
        "pilot_operated_valve": "Pilot-Operated Valve",
        "pressure_sensor": "Pressure Sensor",
        "pressure_indicator": "Pressure Indicator",
        "pressure_element": "Pressure Element",
        "temperature_indicator": "Temperature Indicator",
        "flow_indicator": "Flow Indicator",
        "flow_element": "Flow Element",
        "level_indicator": "Level Indicator",
        "level_switch": "Level Switch",
        "level_switch_low": "Level Switch (Low)",
        "level_switch_high": "Level Switch (High)",
        "level_switch_high_high": "Level Switch (High-High)",
        "measurement_element": "Measurement Element",
        "pressure_vent": "Pressure Vent",
        "emergency_vent": "Emergency Vent",
        "high_point_vent": "High Point Vent",
        "low_point_drain": "Low Point Drain",
        "pressure_relief_valve": "Pressure Relief Valve",
        "temperature_relief_valve": "Temperature Relief Valve",
        "filter_separator": "Filter/Separator",
        "pump_outlet_shutoff_pressure": "Pump Outlet Shutoff Pressure",
        "compressor": "Compressor",
        "vessel": "Vessel",
        "equipment": "Equipment",
    }

    for tag_info in tags:
        tag = tag_info["tag"]
        equipment_type = tag_info.get("type", "equipment")
        description = description_map.get(equipment_type, "Equipment")
        quantity = 1

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


def extract_highlights_from_pdf(file_path: str) -> list[dict[str, object]]:
    """
    Extract highlight annotations from PDF.
    Returns list of highlight bounding boxes and pages.
    """
    if not HAS_PDFPLUMBER:
        return []

    try:
        highlights = []
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                if page.annots:
                    for annot in page.annots:
                        if annot.get("subtype") == "Highlight":
                            highlights.append({
                                "page": page_num,
                                "x0": annot["x0"],
                                "top": annot["top"],
                                "x1": annot["x1"],
                                "bottom": annot["bottom"],
                                "color": annot.get("color", []),
                            })
        return highlights
    except Exception as e:
        print(f"Error extracting highlights from PDF: {e}")
        return []


def tags_within_highlight_box(tags: list[dict], words: list[dict], highlights: list[dict]) -> list[dict]:
    """
    Filter tags to only those whose words fall within highlight bounding boxes.
    """
    if not highlights:
        return tags

    highlighted_tags = []

    for tag_info in tags:
        tag_text = tag_info["tag"]
        # Find words that make up this tag
        tag_parts = tag_text.split("-")

        for word in words:
            word_text = word["text"].upper().replace(" ", "-")
            # Check if word is part of the tag
            if any(part in word_text or word_text in tag_text for part in tag_parts):
                # Check if word is within any highlight box on the same page
                for highlight in highlights:
                    if (word["page"] == highlight["page"] and
                        highlight["x0"] <= word["x0"] <= highlight["x1"] and
                        highlight["top"] <= word["top"] <= highlight["bottom"]):
                        highlighted_tags.append(tag_info)
                        break
                if tag_info in highlighted_tags:
                    break

    # Remove duplicates
    seen = set()
    unique_tags = []
    for tag in highlighted_tags:
        tag_id = tag["tag"]
        if tag_id not in seen:
            seen.add(tag_id)
            unique_tags.append(tag)

    return unique_tags
