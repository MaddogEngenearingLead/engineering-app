from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class ExtractedText:
    text: str
    confidence: float
    bounding_box: tuple[int, int, int, int]


@dataclass
class DetectedSymbol:
    tag: str
    symbol_type: str
    label: str
    confidence: float
    center: tuple[float, float]


@dataclass
class EquipmentNode:
    tag: str
    name: str
    type: str
    x: float
    y: float
    confidence: float


@dataclass
class GraphConnection:
    source: str
    target: str
    connection_type: str = "pipe"
