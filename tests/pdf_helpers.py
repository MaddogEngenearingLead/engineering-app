from __future__ import annotations

import io

from pypdf import PdfReader, PdfWriter
from pypdf.annotations import FreeText, Highlight
from pypdf.generic import ArrayObject, FloatObject
from reportlab.pdfgen import canvas


def build_pdf(path, pages):
    """pages: list of dicts {lines: [str], freetext: [str], highlights: [(tag_line_index, 'rrggbb')]}.

    Each text line is drawn at y = 700 - 40*index; highlight annotations cover that line.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for page in pages:
        for i, line in enumerate(page.get("lines", [])):
            c.drawString(72, 700 - 40 * i, line)
        c.showPage()
    c.save()
    writer = PdfWriter(clone_from=PdfReader(buf))
    for n, page in enumerate(pages):
        for text in page.get("freetext", []):
            writer.add_annotation(n, FreeText(text=text, rect=(300, 100, 560, 140)))
        for idx, colour in page.get("highlights", []):
            y = 700 - 40 * idx
            rect = (70, y - 4, 200, y + 12)
            quad = ArrayObject(FloatObject(v) for v in (70, y + 12, 200, y + 12, 70, y - 4, 200, y - 4))
            writer.add_annotation(n, Highlight(rect=rect, quad_points=quad, highlight_color=colour))
    with open(path, "wb") as f:
        writer.write(f)
    return str(path)
