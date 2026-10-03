from __future__ import annotations

import re
from typing import Any

from app.services.bom_export import export_bom_to_pdf
from app.services.pid_extraction import extract_tags_from_text, generate_bom_from_tags

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


ABBREVIATION_MAP = {
    "A": "Analysis",
    "B": "Burner or combustion",
    "D": "Differential",
    "E": "Voltage",
    "F": "Flow",
    "H": "Hand",
    "I": "Current",
    "J": "Power",
    "K": "Time or rate",
    "L": "Level",
    "M": "Momentary",
    "O": "Orifice or restriction",
    "P": "Pressure",
    "Q": "Quantity",
    "R": "Radiation",
    "S": "Speed or frequency",
    "T": "Temperature",
    "U": "Multivariable",
    "V": "Vibration or mechanical analysis",
    "W": "Weight or force",
    "X": "Unclassified",
    "Y": "Event, state, or presence",
    "Z": "Position",
}

SUCCEEDING_LETTER_MAP = {
    "A": "Alarm",
    "C": "Controller",
    "E": "Element",
    "F": "Ratio",
    "G": "Glass or gauge",
    "I": "Indicator",
    "L": "Light",
    "P": "Point",
    "R": "Recorder",
    "S": "Switch",
    "T": "Transmitter",
    "V": "Valve",
}

COLOUR_MEANINGS = {"red": "demo", "green": "new", "blue": "future"}
LEGEND_KEYWORDS = {
    "legend": 3,
    "instrument key": 4,
    "abbreviation": 2,
    "symbol key": 3,
    "instrumentation": 1,
}
TAG_PATTERN = re.compile(r"\b([A-Z]{1,6})\s*-?\s*(\d{1,4})\b", re.IGNORECASE)


def _normalize_colour(value: Any) -> str | None:
    if isinstance(value, str):
        normalized = value.strip().lower().lstrip("#")
        if normalized in {"red", "green", "blue"}:
            return normalized
        if normalized in {"", "black", "white", "gray", "grey", "transparent", "none"}:
            return None
        if re.fullmatch(r"[0-9a-f]{6}", normalized):
            value = tuple(int(normalized[i:i + 2], 16) / 255 for i in (0, 2, 4))
        else:
            return "other" if normalized else None
    if not isinstance(value, (tuple, list)) or not value:
        return None
    try:
        channels = [float(channel) for channel in value]
    except (TypeError, ValueError):
        return None
    if len(channels) == 1:
        channels *= 3
    elif len(channels) == 4:
        channels = [channels[index] * (1 - channels[3]) for index in range(3)]
    elif len(channels) != 3:
        return None
    if max(channels) > 1:
        channels = [channel / 255 for channel in channels]
    if max(channels) < 0.28 or max(channels) - min(channels) < 0.18:
        return None
    primary_colours = {
        "red": (1, 0, 0),
        "green": (0, 1, 0),
        "blue": (0, 0, 1),
    }
    closest = min(
        primary_colours,
        key=lambda colour: sum(
            (channels[index] - primary_colours[colour][index]) ** 2
            for index in range(3)
        ),
    )
    distance = sum(
        (channels[index] - primary_colours[closest][index]) ** 2
        for index in range(3)
    )
    return closest if distance <= 0.5 else "other"


def extract_content_signatures(pdf_path: str) -> list[dict[str, Any]]:
    """Extract per-page text, equipment tags, and salient colours."""
    if pdfplumber is None:
        raise RuntimeError("PDF processing requires the pdfplumber dependency.")
    signatures = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            tags = extract_tags_from_text(text)
            colours = set()
            for character in page.chars:
                colour = _normalize_colour(
                    character.get("non_stroking_color", character.get("stroking_color"))
                )
                if colour:
                    colours.add(colour)
            for annotation in page.annots or []:
                for key in ("color", " C", "C"):
                    colour = _normalize_colour(annotation.get(key))
                    if colour:
                        colours.add(colour)
            signatures.append({
                "page": page_number,
                "text": text,
                "tags": tags,
                "tag_set": {tag["tag"] for tag in tags},
                "colours": sorted(colours),
            })
    return signatures


def score_legend_candidates(signatures: list[dict[str, Any]]) -> dict[str, Any]:
    """Rank pages likely to contain an instrument legend or key."""
    candidates = []
    for signature in signatures:
        text = signature.get("text", "").lower()
        score = sum(weight * len(re.findall(re.escape(keyword), text))
                    for keyword, weight in LEGEND_KEYWORDS.items())
        if score:
            candidates.append({"page": signature["page"], "score": score})
    candidates.sort(key=lambda candidate: (-candidate["score"], candidate["page"]))
    best = candidates[0] if candidates else None
    return {
        "found": bool(best and best["score"] >= 2),
        "page": best["page"] if best and best["score"] >= 2 else None,
        "score": best["score"] if best else 0,
        "candidates": candidates,
        "source": "keyword_scoring",
    }


def decode_instrument_tag(
    tag: str, abbreviation_map: dict[str, str] | None = None
) -> dict[str, Any]:
    """Decode the first instrument letter and subsequent function letters."""
    letter_map = abbreviation_map if abbreviation_map is not None else ABBREVIATION_MAP
    match = TAG_PATTERN.fullmatch(tag.strip().upper())
    prefix = match.group(1) if match else re.sub(r"[^A-Z]", "", tag.upper())
    if not prefix:
        return {"description": "Equipment", "confidence": 0.25, "source": "fallback"}
    primary = letter_map.get(prefix[0])
    functions = [SUCCEEDING_LETTER_MAP[letter] for letter in prefix[1:]
                 if letter in SUCCEEDING_LETTER_MAP]
    if not primary:
        return {"description": "Equipment", "confidence": 0.25, "source": "unmapped_prefix"}
    description = " ".join([primary, *functions])
    confidence = 0.8 if len(functions) == len(prefix[1:]) else 0.55
    return {
        "description": description,
        "confidence": confidence,
        "source": "instrument_letter_decoder",
        "primary_letter": prefix[0],
        "function_letters": prefix[1:],
    }


def detect_colour_meanings(
    signatures: list[dict[str, Any]], legend: dict[str, Any]
) -> dict[str, Any]:
    """Associate detected drawing colours with the configured work meanings."""
    detected = sorted({colour for signature in signatures for colour in signature.get("colours", [])})
    meanings = dict(COLOUR_MEANINGS)
    evidence = {
        colour: [signature["page"] for signature in signatures
                 if colour in signature.get("colours", [])]
        for colour in detected
    }
    unknown = [colour for colour in detected if colour not in meanings]
    return {
        "meanings": meanings,
        "detected_colours": detected,
        "evidence": evidence,
        "unknown_colours": unknown,
        "legend_page": legend.get("page"),
        "source": "legend_defaults" if legend.get("found") else "configured_colour_convention",
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def classify_pages(
    signatures: list[dict[str, Any]],
    *,
    demo_pages: list[int] | None = None,
    new_work_pages: list[int] | None = None,
    highlight_mapping: dict[str, str] | None = None,
    colour_result: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Classify page roles and work designations with explicit overrides first."""
    demo = set(demo_pages or [])
    new_work = set(new_work_pages or [])
    mappings = {str(key).lower(): str(value).lower()
                for key, value in (highlight_mapping or {}).items()}
    meanings = (colour_result or {}).get("meanings", COLOUR_MEANINGS)
    classifications = []
    for signature in signatures:
        text = signature.get("text", "")
        lowered = text.lower()
        title_score = sum(1 for cue in ("title", "drawing number", "project", "revision")
                          if cue in lowered)
        free_text_score = sum(1 for cue in ("free text", "notes", "scope of work", "description")
                              if cue in lowered)
        if title_score >= 2:
            page_role = "title_page"
        elif free_text_score >= 2:
            page_role = "free_text"
        else:
            page_role = "drawing"
        page = signature["page"]
        colours = signature.get("colours", [])
        tag_overrides = [
            mappings[tag["tag"].lower()] for tag in signature.get("tags", [])
            if tag["tag"].lower() in mappings
        ]
        mapped_colours = [mappings[colour] for colour in colours if colour in mappings]
        if page in demo:
            work_class, source = "demo", "user_override"
        elif page in new_work:
            work_class, source = "new", "user_override"
        elif tag_overrides:
            work_class, source = tag_overrides[0], "highlight_mapping"
        elif mapped_colours:
            work_class, source = mapped_colours[0], "highlight_mapping"
        else:
            work_class = next((meanings.get(colour) for colour in colours if meanings.get(colour)), None)
            source = "colour_legend" if work_class else "content_classification"
        classifications.append({
            "page": page,
            "page_role": page_role,
            "title_score": title_score,
            "free_text_score": free_text_score,
            "work_class": work_class,
            "source": source,
            "colours": colours,
            "tags": sorted(signature.get("tag_set", set())),
        })
    for index, page in enumerate(classifications):
        pairs = []
        tags = set(page["tags"])
        for other in classifications:
            if other["page"] == page["page"]:
                continue
            similarity = _jaccard(tags, set(other["tags"]))
            if similarity > 0:
                pairs.append({"page": other["page"], "similarity": round(similarity, 3)})
        page["similar_pages"] = sorted(pairs, key=lambda pair: (-pair["similarity"], pair["page"]))
    return classifications


def cross_check_scope(
    scope_of_work: str,
    tags: list[dict[str, Any]],
    classifications: list[dict[str, Any]],
) -> dict[str, Any]:
    """Match tag references in the stated scope against extracted drawing tags."""
    extracted = {tag["tag"].upper(): tag["tag"] for tag in tags}
    page_classifications = {page["page"]: page for page in classifications}
    mentioned = []
    for match in TAG_PATTERN.finditer(scope_of_work.upper()):
        normalized = f"{match.group(1)}-{match.group(2)}"
        if normalized not in mentioned:
            mentioned.append(normalized)
    matches = [tag for tag in mentioned if tag in extracted]
    unmatched = [tag for tag in mentioned if tag not in extracted]
    tag_evidence = {}
    ambiguous = []
    for tag in matches:
        tag_info = next(item for item in tags if item["tag"].upper() == tag)
        pages = tag_info.get("pages", [tag_info.get("page")])
        evidence = [
            {
                "page": page,
                "work_class": page_classifications[page]["work_class"],
                "source": page_classifications[page]["source"],
            }
            for page in pages
            if page in page_classifications
        ]
        tag_evidence[tag] = evidence
        work_classes = {item["work_class"] for item in evidence if item["work_class"]}
        if len(work_classes) > 1:
            ambiguous.append(tag)
    return {
        "mentioned_tags": mentioned,
        "matched_tags": matches,
        "unmatched_tags": unmatched,
        "ambiguous_tags": ambiguous,
        "tag_evidence": tag_evidence,
        "status": "needs_clarification" if unmatched or ambiguous else "matched",
    }


def build_scoped_bom(
    pdf_path: str,
    scope_of_work: str = "",
    *,
    demo_pages: list[int] | None = None,
    new_work_pages: list[int] | None = None,
    highlight_mapping: dict[str, str] | None = None,
    review_notes: list[str] | None = None,
    job_id: str,
    source_file: str,
) -> dict[str, Any]:
    """Build a scoped BOM and return evidence, clarification, and export status."""
    signatures = extract_content_signatures(pdf_path)
    page_count = len(signatures)
    conflicting_pages = sorted(set(demo_pages or []) & set(new_work_pages or []))
    if conflicting_pages:
        raise ValueError(
            "Pages cannot be designated as both demo and new work: "
            + ", ".join(map(str, conflicting_pages))
        )
    invalid_pages = sorted(
        page for page in (demo_pages or []) + (new_work_pages or [])
        if page < 1 or page > page_count
    )
    if invalid_pages:
        raise ValueError(
            f"Page overrides are outside the document range (1-{page_count}): "
            + ", ".join(map(str, invalid_pages))
        )
    legend = score_legend_candidates(signatures)
    colour_result = detect_colour_meanings(signatures, legend)
    pages = classify_pages(
        signatures,
        demo_pages=demo_pages,
        new_work_pages=new_work_pages,
        highlight_mapping=highlight_mapping,
        colour_result=colour_result,
    )
    tags_by_name: dict[str, dict[str, Any]] = {}
    for signature in signatures:
        for tag in signature["tags"]:
            enriched = tags_by_name.setdefault(
                tag["tag"],
                {**tag, "page": signature["page"], "pages": []},
            )
            if signature["page"] not in enriched["pages"]:
                enriched["pages"].append(signature["page"])
    tags = list(tags_by_name.values())
    materials = generate_bom_from_tags(tags)
    classification_by_page = {page["page"]: page for page in pages}
    for material, tag in zip(materials, tags):
        decoded = decode_instrument_tag(tag["tag"])
        if tag.get("type", "") not in {
            "level_switch_low", "level_switch_high", "level_switch_high_high"
        } and tag.get("type", "").endswith(("indicator", "sensor", "element", "switch")):
            material["description"] = decoded["description"]
            material["description_confidence"] = decoded["confidence"]
            material["description_source"] = decoded["source"]
        else:
            material["description_confidence"] = tag.get("confidence", 0.85)
            material["description_source"] = tag.get("source", "tag_type_mapping")
        page = classification_by_page.get(tag.get("page"))
        material["work_class"] = page["work_class"] if page else None
        material["classification_source"] = page["source"] if page else "unknown"
        material["source_page"] = tag.get("page")
    scope_check = cross_check_scope(scope_of_work, tags, pages)
    prompts = []
    if tags and not legend["found"]:
        prompts.append("Confirm the instrument legend or key; no page scored as a legend.")
    if colour_result["unknown_colours"]:
        prompts.append(
            "Clarify the meaning of detected colours: "
            + ", ".join(colour_result["unknown_colours"])
            + "."
        )
    if scope_check["unmatched_tags"]:
        prompts.append(
            "Confirm scope tags not found in the P&ID: "
            + ", ".join(scope_check["unmatched_tags"])
            + "."
        )
    if scope_check["ambiguous_tags"]:
        prompts.append(
            "Clarify tags assigned to conflicting work classes: "
            + ", ".join(scope_check["ambiguous_tags"])
            + "."
        )
    if not tags:
        prompts.append("No equipment tags were extracted; provide OCR text or confirm the source drawing.")
    prompts.extend(review_notes or [])
    needs_clarification = bool(prompts)
    export_path = None
    export_error = None
    if materials:
        try:
            export_path = export_bom_to_pdf(
                job_id=job_id,
                source_file=source_file,
                materials=materials,
                scope_of_work=scope_of_work,
                review_notes=prompts,
            )
        except Exception as error:
            export_error = str(error)
    return {
        "detected_assets": tags,
        "materials": materials,
        "page_classifications": pages,
        "scope_check": scope_check,
        "legend": legend,
        "colour_analysis": colour_result,
        "needs_clarification": needs_clarification,
        "clarification_prompts": prompts,
        "bom_pdf": export_path,
        "export_status": (
            "failed" if export_error else "provisional" if export_path and needs_clarification
            else "completed" if export_path else "not_generated"
        ),
        "export_error": export_error,
        "extracted_text_length": sum(len(signature["text"]) for signature in signatures),
    }
