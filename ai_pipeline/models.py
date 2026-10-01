from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any


@dataclass
class PageMetadata:
    page_number: int
    width: float
    height: float
    rotation: int = 0


@dataclass
class ExtractedText:
    text: str
    confidence: float
    bounding_box: tuple[int, int, int, int]
    page_number: int = 0


@dataclass
class DetectedSymbol:
    tag: str
    symbol_type: str
    label: str
    confidence: float
    center: tuple[float, float]
    page_number: int = 0
    bounding_box: tuple[int, int, int, int] = field(default_factory=tuple)


@dataclass
class EquipmentNode:
    tag: str
    name: str
    type: str
    x: float
    y: float
    confidence: float
    page_number: int = 0


@dataclass
class GraphConnection:
    source: str
    target: str
    connection_type: str = "pipe"


@dataclass
class DocumentPage:
    page_number: int
    text_blocks: list[ExtractedText] = field(default_factory=list)
    symbols: list[DetectedSymbol] = field(default_factory=list)
    metadata: PageMetadata = field(default_factory=lambda: PageMetadata(0, 0, 0))
