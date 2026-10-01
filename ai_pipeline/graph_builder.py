from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

import networkx as nx


def build_topology_graph(detected_symbols: list[dict[str, Any]], extracted_text: list[dict[str, Any]]) -> nx.Graph:
    """Builds a graph where nodes represent equipment and edges represent piping relationships."""
    graph = nx.Graph()
    tag_candidates = []

    for item in extracted_text:
        text = item.get("text", "")
        matches = re.findall(r"[A-Z]+-\d+", text)
        tag_candidates.extend(matches)

    tag_candidates = sorted(set(tag_candidates))

    for idx, symbol in enumerate(detected_symbols):
        label = symbol.get("label", "Equipment")
        symbol_type = symbol.get("symbol_type", "unknown")
        tag = tag_candidates[idx] if idx < len(tag_candidates) else f"AUTO-{idx + 1}"
        center = symbol.get("center", (0.0, 0.0))

        graph.add_node(
            tag,
            name=f"{label} {tag}",
            type=symbol_type,
            x=center[0],
            y=center[1],
            confidence=symbol.get("confidence", 0.0),
        )

    for node_a, node_b in zip(list(graph.nodes)[:-1], list(graph.nodes)[1:]):
        graph.add_edge(node_a, node_b, type="pipe")

    return graph
