from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np
from PIL import Image


def detect_basic_shapes(image_path: str) -> list[dict[str, Any]]:
    """Heuristic detector for common P&ID symbols using image contours.

    This lightweight implementation is meant as a production-ready starter that can be upgraded to YOLOv8 later.
    """
    image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FileNotFoundError(f"Unable to read image: {image_path}")

    edges = cv2.Canny(image, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    results: list[dict[str, Any]] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 200:
            continue

        x, y, w, h = cv2.boundingRect(contour)
        aspect = w / max(h, 1)

        if aspect > 1.8:
            symbol_type = "pipe_segment"
            label = "Pipe"
        elif w < 90 and h < 90:
            symbol_type = "instrument"
            label = "Instrument"
        elif aspect >= 0.7 and aspect <= 1.3:
            symbol_type = "vessel"
            label = "Vessel"
        elif aspect < 0.7:
            symbol_type = "valve"
            label = "Valve"
        else:
            symbol_type = "pump"
            label = "Pump"

        cx = x + w / 2
        cy = y + h / 2
        results.append(
            {
                "label": label,
                "symbol_type": symbol_type,
                "area": float(area),
                "center": (float(cx), float(cy)),
                "bounding_box": [x, y, w, h],
                "confidence": min(0.99, max(0.55, area / 5000.0)),
            }
        )

    return results


def infer_tag_candidates(text_results: list[dict[str, Any]]) -> list[str]:
    tags: list[str] = []
    for item in text_results:
        text = item.get("text", "")
        matches = re.findall(r"[A-Z]+-\d+", text)
        if matches:
            tags.extend(matches)
    return sorted(set(tags))


def detect_symbols(image_path: str) -> list[dict[str, Any]]:
    """Public entry point for symbol detection."""
    return detect_basic_shapes(image_path)
