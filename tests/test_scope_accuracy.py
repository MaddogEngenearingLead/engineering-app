from __future__ import annotations

import io

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import FreeText
from reportlab.pdfgen import canvas

from app.services import scope_bom as sb
from app.services.pid_extraction import extract_tags_from_text

LEGEND = [
    "LEGEND",
    "TK    STORAGE TANK",
    "PCV   PRESSURE CONTROL VALVE",
    "VFD   VARIABLE FREQUENCY DRIVE",
    "JFSP  FUEL PUMP",
    "INSTRUMENT IDENTIFICATION",
    "FIRST LETTER",
    "P  PRESSURE",
    "SUCCEEDING LETTERS",
    "A  ALARM",
    "H  HIGH",
]


def _text(c, lines, x=50, y=780):
    c.setFillColorRGB(0, 0, 0)
    for line in lines:
        c.drawString(x, y, line)
        y -= 20


def build_pid(path):
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    _text(c, LEGEND)
    c.showPage()

    # page 2: demo
    _text(c, ["TK-1 existing tank", "PI-9 gauge", "JFSP-2A old pump"])
    c.showPage()

    # page 3: new work. TK-1 sits in a green highlight, a green box has no tag
    _text(c, ["", "PI-9 gauge", "PCV-101 control valve", "VFD-1 drive",
              "JFSP-2A pump", "JFSP-2B pump", "PAH-5 pressure alarm", "ZZQ-7 mystery"])
    c.setFillColorRGB(0, 1, 0)
    c.rect(45, 770, 120, 18, fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(50, 780, "TK-1 tank")
    c.setFillColorRGB(0, 1, 0)
    c.rect(300, 600, 160, 18, fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(305, 605, "NEW 4IN FLANGE")
    c.showPage()
    c.save()
    buf.seek(0)

    writer = PdfWriter()
    writer.append(PdfReader(buf))
    for idx, text in ((1, "DEMO DRAWING"), (2, "NEW INSTALLATION DRAWING")):
        writer.add_annotation(page_number=idx, annotation=FreeText(text=text, rect=(50, 500, 300, 540)))
    with open(path, "wb") as f:
        writer.write(f)
    return str(path)


@pytest.fixture
def pid(tmp_path):
    return build_pid(tmp_path / "pid.pdf")


def scan(pid, tmp_path, scope):
    return sb.build_scoped_bom(pid, scope_text=scope, output_dir=str(tmp_path / "out"))


def test_tag_letter_suffix_and_extra_prefix():
    tags = {t["tag"] for t in extract_tags_from_text("JFSP-2A and JFSP-2B, PCV 101", ["PCV"])}
    assert tags == {"JFSP-2A", "JFSP-2B", "PCV-101"}
    assert "PCV-101" not in {t["tag"] for t in extract_tags_from_text("PCV-101")}


def test_legend_table_and_key_sections():
    legend = sb.parse_legend("\n".join(LEGEND))
    assert legend["PCV"] == "Pressure Control Valve" and legend["VFD"] == "Variable Frequency Drive"
    assert "LEGEND" not in legend
    key = sb.parse_instrument_key("\n".join(LEGEND))
    assert key["first_letters"]["P"] == "Pressure" and key["succeeding_letters"]["H"] == "High"


def test_scan_uses_legend_and_scope(pid, tmp_path):
    scope = "Install PCV-101 and the VFD-1 drive. Replace tank TK-1. Add a new 4in flange."
    r = scan(pid, tmp_path, scope)
    assert r["status"] == "completed"
    assert r["legend"]["page"] == 1 and r["legend"]["entries_found"] >= 4

    by_tag = {m["tag_id"]: m for m in r["materials"]}
    # legend-defined prefixes are now found and described from the legend
    assert by_tag["PCV-101"]["description"] == "Pressure Control Valve"
    assert by_tag["VFD-1"]["description_source"] == "legend"
    # letter-suffixed tags are separate items
    assert "JFSP-2B" in by_tag
    # decoded through the instrument identification key
    assert by_tag["PAH-5"]["description"] == "Pressure Alarm High"
    # highlighted existing tank is kept even though it is on the demo page
    assert by_tag["TK-1"]["highlighted"] is True
    # unchanged, un-highlighted, not in scope -> excluded and reported
    assert "PI-9" not in by_tag
    assert any(e["tag"] == "PI-9" for e in r["excluded_items"])
    # highlighted new-work item with no tag is on the BOM
    flange = [m for m in r["materials"] if m["type"] == "highlighted_item"]
    assert flange and "Flange" in flange[0]["description"]
    # unexplained tag-like items are reported instead of silently dropped
    assert any(f["type"] == "unidentified_tags" and "ZZQ-7" in f["tags"] for f in r["flags"])


def test_csv_has_consistent_columns(pid, tmp_path):
    r = scan(pid, tmp_path, "Install PCV-101.")
    import csv
    with open(r["bom_csv"]) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(r["materials"]) and "basis" in rows[0]


def test_no_text_page_is_flagged(tmp_path):
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.showPage()
    c.save()
    path = tmp_path / "blank.pdf"
    path.write_bytes(buf.getvalue())
    import pdfplumber
    with pdfplumber.open(str(path)) as pdf:
        sigs = [sb.extract_page_content_signature(pdf, 1)]
    assert sb._no_text_pages(sigs) == [1]


def test_scope_items_from_install_lines():
    from app.services.pid_scope import scope_items
    text = ("Demo: pad\nDemolish tank 1 sight glass.\n(DRG. M-601-0) Installation: pad\n"
            "Install (2) 3/4\u201d plugs one on top and one on bottom of tank\n"
            "Install new 4\u201d 150# pneumatic operated valve on inlet piping\n")
    items = {i["description"]: i["quantity"] for i in scope_items(text)}
    assert items['3/4" Plug'] == 2
    assert items['4" 150# Pneumatic Operated Valve w/ Operator'] == 1
