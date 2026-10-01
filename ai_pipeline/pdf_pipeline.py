from __future__ import annotations

import re
from typing import Any
from pathlib import Path

from ai_pipeline.pdf_processor import PDFProcessor, EngineeringDocumentParser
from ai_pipeline.ocr import extract_text_from_image
from ai_pipeline.symbol_detector import detect_symbols
from ai_pipeline.graph_builder import build_topology_graph
from ai_pipeline.models import DocumentPage


def process_pdf_pid_file(file_path: str) -> dict[str, Any]:
    """End-to-end pipeline for processing PDF P&ID files."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"P&ID file not found: {file_path}")

    # Extract text and tables from PDF
    pdf_pages: list[DocumentPage] = PDFProcessor.extract_text_from_pdf(str(path))
    tables = PDFProcessor.extract_tables_from_pdf(str(path))

    # Flatten text blocks from all pages
    all_text_blocks = []
    for page in pdf_pages:
        all_text_blocks.extend(page.text_blocks)

    # Extract equipment tags from text
    equipment_from_text = EngineeringDocumentParser.extract_equipment_from_text(all_text_blocks)

    # Extract BOM items from tables
    bom_items = EngineeringDocumentParser.extract_bom_from_tables(tables)

    # Convert PDF pages to images for symbol detection
    try:
        image_paths = PDFProcessor.convert_pdf_pages_to_images(str(path))
        all_symbols = []
        for img_path in image_paths:
            symbols = detect_symbols(img_path)
            all_symbols.extend(symbols)
    except Exception as e:
        print(f"Warning: Could not convert PDF to images for symbol detection: {e}")
        all_symbols = []

    # Merge equipment from text and symbols
    equipment = []
    seen_tags = set()

    # Add equipment from text extraction (higher priority)
    for eq in equipment_from_text:
        tag = eq.get("tag", "")
        if tag and tag not in seen_tags:
            equipment.append(eq)
            seen_tags.add(tag)

    # Add inferred equipment from BOM tables
    for bom_item in bom_items:
        tag = bom_item.get("tag", "")
        if tag and tag not in seen_tags:
            equipment.append(
                {
                    "tag": tag,
                    "type": EngineeringDocumentParser.infer_equipment_type(
                        bom_item.get("description", ""), tag
                    ),
                    "source_text": bom_item.get("description", ""),
                    "confidence": 0.9,
                    "page_number": 0,
                    "bounding_box": (0, 0, 0, 0),
                }
            )
            seen_tags.add(tag)

    # Add equipment from symbol detection (lower priority)
    for symbol_idx, symbol in enumerate(all_symbols):
        inferred_tag = equipment_from_text[symbol_idx]["tag"] if symbol_idx < len(equipment_from_text) else f"AUTO-{symbol_idx + 1}"
        if inferred_tag not in seen_tags:
            equipment.append(
                {
                    "tag": inferred_tag,
                    "type": symbol.get("symbol_type", "equipment"),
                    "label": symbol.get("label", ""),
                    "confidence": symbol.get("confidence", 0.0),
                    "page_number": 0,
                    "bounding_box": symbol.get("bounding_box", (0, 0, 0, 0)),
                }
            )
            seen_tags.add(inferred_tag)

    # Build topology graph
    graph = build_topology_graph(all_symbols, all_text_blocks)

    return {
        "status": "processed",
        "file_type": "pdf",
        "pages_processed": len(pdf_pages),
        "text_blocks_extracted": len(all_text_blocks),
        "tables_extracted": len(tables),
        "equipment": equipment,
        "equipment_count": len(equipment),
        "bom_items": bom_items,
        "bom_count": len(bom_items),
        "pdf_pages": [
            {
                "page_number": page.page_number,
                "text_blocks_count": len(page.text_blocks),
                "symbols_count": len(page.symbols),
                "metadata": {
                    "width": page.metadata.width,
                    "height": page.metadata.height,
                    "rotation": page.metadata.rotation,
                },
            }
            for page in pdf_pages
        ],
        "tables": tables,
        "graph_nodes": list(graph.nodes(data=True)),
        "graph_edges": list(graph.edges(data=True)),
    }
