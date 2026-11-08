from __future__ import annotations

import io
import re

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import FreeText
from reportlab.pdfgen import canvas

LEGEND_LINES = ["LEGEND", "TK - Storage Tank", "JFSP - Fuel Pump", "POV - Pilot Operated Valve"]


def make_pdf(path, pages, freetext=None):
    """pages: list of (lines, rgb); freetext: {page_index: text}."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for lines, rgb in pages:
        c.setFillColorRGB(*rgb)
        y = 780
        for line in lines:
            c.drawString(50, y, line)
            y -= 20
        c.showPage()
    c.save()
    buf.seek(0)
    writer = PdfWriter()
    writer.append(PdfReader(buf))
    for idx, text in (freetext or {}).items():
        writer.add_annotation(
            page_number=idx,
            annotation=FreeText(text=text, rect=(50, 600, 300, 640)),
        )
    with open(path, "wb") as f:
        writer.write(f)
    return str(path)


@pytest.fixture
def freetext_pdf(tmp_path):
    shape = ["TK-1 storage", "JFSP-1 pump", "POV-1 valve"]
    return make_pdf(
        tmp_path / "ft.pdf",
        [
            (LEGEND_LINES, (0, 0, 0)),
            (shape, (1, 0, 0)),
            (shape + ["PI-2 gauge"], (0, 1, 0)),
        ],
        freetext={1: "DEMO DRAWING", 2: "NEW INSTALLATION DRAWING"},
    )


@pytest.fixture
def ambiguous_pdf(tmp_path):
    shape = ["TK-1 storage", "JFSP-1 pump", "POV-1 valve"]
    return make_pdf(
        tmp_path / "amb.pdf",
        [
            (LEGEND_LINES, (0, 0, 0)),
            (shape, (1, 0, 0)),
            (shape + ["PI-2 gauge"], (0, 1, 0)),
        ],
    )


@pytest.fixture
def required_ai(monkeypatch):
    """Provide deterministic AI responses to tests of scan orchestration."""
    from app.services import ai_review

    class TestProvider:
        name = "test"
        model = "test-model"

    def draft_scope(drawing, bom, review_index="", provider=None):
        source_ids = list(dict.fromkeys(re.findall(r"\b(?:AI-BOM-\d+|BOM-\d+|P\d+)\b",
                                                    drawing + "\n" + bom)))
        tasks = [{"text": line.lstrip("- ").strip(), "sources": [source_ids[0]], "verify": True}
                 for line in review_index.splitlines() if line.strip() and source_ids]
        if not tasks and source_ids:
            tasks = [{"text": "Confirm the intended work against the source drawings.",
                      "sources": [source_ids[0]], "verify": True}]
        return {"sections": [{"title": "Review source evidence", "tasks": tasks}],
                "provider": "test", "model": "test-model"}

    monkeypatch.setattr(ai_review, "get_provider", lambda *_args, **_kwargs: TestProvider())
    monkeypatch.setattr(ai_review, "review_with_ai", lambda *_args, **_kwargs: {
        "flags": [], "summary": "Reviewed source evidence.", "key_page": None,
        "provider": "test", "model": "test-model"})
    monkeypatch.setattr(ai_review, "draft_scope_with_ai", draft_scope)
