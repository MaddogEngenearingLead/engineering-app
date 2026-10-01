from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_pipeline.ocr import extract_text_from_image
from ai_pipeline.symbol_detector import detect_symbols, infer_tag_candidates
from ai_pipeline.graph_builder import build_topology_graph


def process_pid_file(file_path: str) -> dict[str, Any]:
    """End-to-end pipeline for a single uploaded P&ID."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"P&ID file not found: {file_path}")

    ocr_results = extract_text_from_image(str(path))
    symbols = detect_symbols(str(path))
    inferred_tags = infer_tag_candidates(ocr_results)

    graph = build_topology_graph(symbols, ocr_results)

    equipment = []
    for symbol in symbols:
        tag = inferred_tags[len(equipment)] if len(equipment) < len(inferred_tags) else f"AUTO-{len(equipment) + 1}"
        equipment.append(
            {
                "tag": tag,
                "type": symbol.get("symbol_type", "unknown"),
                "label": symbol.get("label", "Equipment"),
                "confidence": symbol.get("confidence", 0.0),
                "center": symbol.get("center", (0.0, 0.0)),
            }
        )

    return {
        "status": "processed",
        "ocr_results": ocr_results,
        "detected_symbols": symbols,
        "inferred_tags": inferred_tags,
        "equipment": equipment,
        "graph_nodes": list(graph.nodes(data=True)),
        "graph_edges": list(graph.edges(data=True)),
    }
