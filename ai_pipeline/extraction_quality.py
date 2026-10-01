from __future__ import annotations

import re
from typing import Any


class EngineeringTextCleaner:
    """Cleans and normalizes engineering text extracted from PDFs and scans."""

    TAG_PATTERNS = [
        r"\b[A-Z]{1,3}-\d{2,4}\b",
        r"\b[A-Z]{1,3}\d{2,4}[A-Z]?\b",
        r"\b[A-Z]{2,4}\s*[-/]\s*\d{2,4}\b",
    ]

    @staticmethod
    def normalize_whitespace(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def clean_text(value: str) -> str:
        cleaned = value.replace("\xa0", " ")
        cleaned = re.sub(r"[\t\r\n]+", " ", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        cleaned = cleaned.strip()
        return cleaned

    @staticmethod
    def extract_tags(value: str) -> list[str]:
        tags: list[str] = []
        for pattern in EngineeringTextCleaner.TAG_PATTERNS:
            tags.extend(re.findall(pattern, value))
        return sorted(set(tags))

    @staticmethod
    def normalize_tag(value: str) -> str:
        tag = EngineeringTextCleaner.clean_text(value)
        tag = tag.replace(" ", "")
        return tag

    @staticmethod
    def infer_equipment_from_tag(tag: str) -> str:
        tag_prefix = tag[:1].upper()
        mapping = {
            "P": "pump",
            "V": "valve",
            "E": "vessel",
            "C": "compressor",
            "F": "filter",
            "T": "tank",
            "X": "heat_exchanger",
            "I": "instrument",
            "M": "motor",
        }
        return mapping.get(tag_prefix, "equipment")


class ExtractionQualityScorer:
    """Scores the quality of extracted data for engineering documents."""

    @staticmethod
    def score_text_block(block: dict[str, Any]) -> float:
        text = (block.get("text") or "").strip()
        confidence = float(block.get("confidence", 0.0))
        score = confidence

        if not text:
            return 0.0

        if re.search(r"[A-Z]{1,3}-\d{2,4}", text):
            score += 0.2
        if re.search(r"\b(pump|valve|vessel|tank|compressor|instrument)\b", text.lower()):
            score += 0.2
        if len(text) > 10:
            score += 0.05

        return min(score, 1.0)

    @staticmethod
    def score_bom_item(item: dict[str, Any]) -> float:
        score = 0.5
        if item.get("tag"):
            score += 0.2
        if item.get("description"):
            score += 0.2
        if item.get("quantity") is not None:
            score += 0.1
        return min(score, 1.0)


class EngineeringPatternMatcher:
    """Matching rules for common engineering document patterns."""

    @staticmethod
    def find_bom_columns(headers: list[str]) -> dict[str, int]:
        normalized = [h.lower() for h in headers]
        mapping = {
            "tag": next((i for i, h in enumerate(normalized) if "tag" in h or "id" in h), 0),
            "description": next((i for i, h in enumerate(normalized) if "desc" in h or "equipment" in h or "item" in h), 1),
            "quantity": next((i for i, h in enumerate(normalized) if "qty" in h or "quantity" in h or "qty" in h), 2),
            "unit": next((i for i, h in enumerate(normalized) if "unit" in h or "uom" in h), 3),
        }
        return mapping

    @staticmethod
    def infer_flow_direction(text: str) -> str:
        lower = text.lower()
        if "to" in lower or "outlet" in lower:
            return "forward"
        if "from" in lower or "inlet" in lower:
            return "reverse"
        return "bidirectional"


class DocumentQualityAssessor:
    """Flags extraction quality and confidence for engineering document processing."""

    @staticmethod
    def assess(page_count: int, text_blocks: int, equipment: int, bom_items: int) -> dict[str, Any]:
        quality = 0.0
        quality += min(page_count * 0.1, 0.2)
        quality += min(text_blocks * 0.01, 0.25)
        quality += min(equipment * 0.08, 0.30)
        quality += min(bom_items * 0.07, 0.25)

        return {
            "quality_score": round(min(quality, 1.0), 2),
            "status": "high" if quality >= 0.7 else "medium" if quality >= 0.4 else "low",
            "notes": "Extraction quality is acceptable for engineering review." if quality >= 0.7 else "Manual review recommended for low-confidence results.",
        }


class PDFExtractionEnhancer:
    """Enhances PDF extraction for real P&ID documents."""

    @staticmethod
    def enhance_text_blocks(text_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        enhanced = []
        for block in text_blocks:
            cleaned = EngineeringTextCleaner.clean_text(block.get("text", ""))
            tags = EngineeringTextCleaner.extract_tags(cleaned)
            normalized = {"text": cleaned, "confidence": ExtractionQualityScorer.score_text_block(block), "tags": tags}
            enhanced.append(normalized)
        return enhanced

    @staticmethod
    def enhance_bom_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        enhanced = []
        for item in items:
            tag = item.get("tag")
            if tag:
                normalized_tag = EngineeringTextCleaner.normalize_tag(tag)
                item["tag"] = normalized_tag
                item["type"] = EngineeringTextCleaner.infer_equipment_from_tag(normalized_tag)
            item["quality_score"] = ExtractionQualityScorer.score_bom_item(item)
            enhanced.append(item)
        return enhanced

    @staticmethod
    def enrich_equipment(equipment: list[dict[str, Any]]) -> list[dict[str, Any]]:
        enhanced = []
        for item in equipment:
            tag = item.get("tag")
            if tag:
                normalized_tag = EngineeringTextCleaner.normalize_tag(tag)
                item["tag"] = normalized_tag
                item["type"] = item.get("type") or EngineeringTextCleaner.infer_equipment_from_tag(normalized_tag)
            item["quality_score"] = float(item.get("confidence", 0.0))
            enhanced.append(item)
        return enhanced
