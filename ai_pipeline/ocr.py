from __future__ import annotations

import re
from typing import Any

from PIL import Image

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None


def extract_text_from_image(image_path: str) -> list[dict[str, Any]]:
    """OCR wrapper for extracting text from uploaded P&ID images."""
    if pytesseract is None:
        return [
            {
                "text": "OCR engine unavailable",
                "confidence": 0.0,
                "bounding_box": [0, 0, 0, 0],
            }
        ]

    img = Image.open(image_path)
    text = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    results: list[dict[str, Any]] = []
    for i, word in enumerate(text["text"]):
        cleaned = word.strip()
        if not cleaned:
            continue

        if re.search(r"[A-Z]-?\d+", cleaned):
            results.append(
                {
                    "text": cleaned,
                    "confidence": float(text["conf"][i]) / 100.0 if text["conf"][i] != "-1" else 0.0,
                    "bounding_box": [
                        int(text["left"][i]),
                        int(text["top"][i]),
                        int(text["width"][i]),
                        int(text["height"][i]),
                    ],
                }
            )

    if not results:
        return [
            {
                "text": "No tag candidates detected",
                "confidence": 0.0,
                "bounding_box": [0, 0, 0, 0],
            }
        ]

    return results
