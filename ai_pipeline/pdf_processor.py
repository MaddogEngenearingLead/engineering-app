from __future__ import annotations

import io
from pathlib import Path
from typing import Any

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    from PIL import Image
import pytesseract
except ImportError:
    Image = None
    pytesseract = None

from ai_pipeline.models import ExtractedText, DocumentPage, PageMetadata


class PDFProcessor:
    """Extracts structured text and tables from PDF engineering documents."""

    @staticmethod
    def extract_text_from_pdf(pdf_path: str) -> list[DocumentPage]:
        """Extract text blocks from all pages of a PDF using pdfplumber."""
        if pdfplumber is None:
            raise ImportError("pdfplumber is required for PDF processing. Install it with: pip install pdfplumber")

        pages_data: list[DocumentPage] = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_idx, page in enumerate(pdf.pages, start=1):
                    page_data = DocumentPage(page_number=page_idx)
                    page_data.metadata = PageMetadata(
                        page_number=page_idx,
                        width=page.width,
                        height=page.height,
                        rotation=page.rotation or 0,
                    )

                    # Extract text with bounding boxes
                    for text_block in page.extract_text_lines() or []:
                        text = text_block.get("text", "").strip()
                        if text:
                            x0 = text_block.get("x0", 0)
                            top = text_block.get("top", 0)
                            x1 = text_block.get("x1", 0)
                            bottom = text_block.get("bottom", 0)

                            extracted = ExtractedText(
                                text=text,
                                confidence=0.95,  # pdfplumber is highly reliable
                                bounding_box=(int(x0), int(top), int(x1 - x0), int(bottom - top)),
                                page_number=page_idx,
                            )
                            page_data.text_blocks.append(extracted)

                    pages_data.append(page_data)
        except Exception as e:
            raise RuntimeError(f"Failed to process PDF: {e}")

        return pages_data

    @staticmethod
    def extract_tables_from_pdf(pdf_path: str) -> list[dict[str, Any]]:
        """Extract tables (BOM, equipment lists, etc.) from PDF pages."""
        if pdfplumber is None:
            raise ImportError("pdfplumber is required for PDF processing.")

        tables: list[dict[str, Any]] = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_idx, page in enumerate(pdf.pages, start=1):
                    for table_idx, table in enumerate(page.extract_tables() or [], start=1):
                        if table:
                            tables.append(
                                {
                                    "page_number": page_idx,
                                    "table_index": table_idx,
                                    "rows": table,
                                    "header": table[0] if table else [],
                                    "data_rows": table[1:] if len(table) > 1 else [],
                                }
                            )
        except Exception as e:
            raise RuntimeError(f"Failed to extract tables from PDF: {e}")

        return tables

    @staticmethod
    def convert_pdf_pages_to_images(pdf_path: str, output_dir: str | None = None) -> list[str]:
        """Convert PDF pages to images for symbol detection."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("PyMuPDF (fitz) is required. Install with: pip install PyMuPDF")

        if output_dir is None:
            output_dir = str(Path(pdf_path).parent / "pdf_pages")

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        image_paths: list[str] = []

        try:
            doc = fitz.open(pdf_path)
            for page_idx, page in enumerate(doc, start=1):
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)  # 2x zoom for better OCR
                image_file = output_path / f"page_{page_idx:03d}.png"
                pix.save(str(image_file))
                image_paths.append(str(image_file))
            doc.close()
        except Exception as e:
            raise RuntimeError(f"Failed to convert PDF pages to images: {e}")

        return image_paths


class EngineeringDocumentParser:
    """Specialized parser for P&ID and engineering documents."""

    # Common equipment tag patterns in engineering documents
    EQUIPMENT_PATTERNS = {
        r"[A-Z]{1,3}-\d{2,4}": "standard_tag",  # P-101, V-201, E-1001
        r"[A-Z]{2}\d{2,4}[A-Z]?": "variant_tag",  # P101A, V201B
        r"TAG\s*[:=]?\s*([A-Z0-9-]+)": "labeled_tag",
    }

    EQUIPMENT_TYPES = {
        "pump": ["pump", "centrifugal", "reciprocating", "gear pump"],
        "valve": ["valve", "gate", "globe", "check", "ball"],
        "vessel": ["vessel", "tank", "column", "reactor", "separator"],
        "compressor": ["compressor", "screw compressor", "reciprocating compressor"],
        "instrument": ["instrument", "transmitter", "gauge", "indicator"],
        "heat_exchanger": ["heat exchanger", "cooler", "heater"],
        "filter": ["filter", "strainer"],
    }

    @staticmethod
    def extract_equipment_from_text(text_blocks: list[ExtractedText]) -> list[dict[str, Any]]:
        """Extract equipment tags and metadata from text blocks."""
        import re

        equipment: list[dict[str, Any]] = []
        seen_tags: set[str] = set()

        for block in text_blocks:
            text = block.text

            # Try standard tag pattern first
            matches = re.findall(r"[A-Z]{1,3}-\d{2,4}", text)
            for match in matches:
                if match not in seen_tags:
                    equipment.append(
                        {
                            "tag": match,
                            "type": "equipment",
                            "source_text": text,
                            "confidence": block.confidence,
                            "page_number": block.page_number,
                            "bounding_box": block.bounding_box,
                        }
                    )
                    seen_tags.add(match)

        return equipment

    @staticmethod
    def infer_equipment_type(description: str, tag: str) -> str:
        """Infer equipment type from description text or tag."""
        description_lower = description.lower()

        for eq_type, keywords in EngineeringDocumentParser.EQUIPMENT_TYPES.items():
            if any(kw in description_lower for kw in keywords):
                return eq_type

        # Fallback to tag-based inference
        tag_first_char = tag[0] if tag else ""
        type_map = {"P": "pump", "V": "valve", "E": "vessel", "C": "compressor", "I": "instrument"}
        return type_map.get(tag_first_char, "equipment")

    @staticmethod
    def extract_bom_from_tables(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Extract bill of materials from extracted tables."""
        bom_items: list[dict[str, Any]] = []
        item_number = 1

        for table in tables:
            header = table.get("header", [])
            data_rows = table.get("data_rows", [])

            # Look for common BOM column patterns
            tag_col = None
            desc_col = None
            qty_col = None

            if header:
                header_lower = [str(h).lower() for h in header]
                tag_col = next((i for i, h in enumerate(header_lower) if "tag" in h or "id" in h), 0)
                desc_col = next((i for i, h in enumerate(header_lower) if "desc" in h or "equipment" in h), 1)
                qty_col = next((i for i, h in enumerate(header_lower) if "qty" in h or "quantity" in h), 2)

            for row in data_rows:
                if row and len(row) > 0:
                    tag = str(row[tag_col] if tag_col < len(row) else f"AUTO-{item_number}").strip()
                    description = str(row[desc_col] if desc_col < len(row) else "Equipment").strip()
                    quantity = 1

                    try:
                        if qty_col < len(row):
                            quantity = int(row[qty_col])
                    except (ValueError, TypeError):
                        quantity = 1

                    bom_items.append(
                        {
                            "item_number": item_number,
                            "tag": tag,
                            "description": description,
                            "quantity": quantity,
                            "unit": "ea",
                            "type": "equipment",
                        }
                    )
                    item_number += 1

        return bom_items
