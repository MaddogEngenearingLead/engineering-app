import shutil
import json

import pytest
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

from app.services.embedded_bom import _columns, _qty, _scope_reference, _type_of
from app.services.scope_bom import build_scoped_bom


def test_qty_forms():
    assert _qty("9") == (9, "ea", "")
    assert _qty("+/- 160'") == (160, "ft", "")
    assert _qty("AS REQ.") == (None, "", "")
    assert _qty("AS REQUIRED") == (None, "", "")
    assert _qty("BY FIELD") == (None, "", "")
    assert _qty("FIELD VERIFY") == (None, "", "")
    assert _qty("")[2] == "Quantity not stated (as required / by field)"


def test_type_and_columns():
    assert _type_of('2", THREDOLET FOR 8" THRU 10" PIPE') == "fitting"
    assert _type_of('120 DEGREE FRP PAD, 12" LONG FOR 8" PIPE') == "support"
    assert _type_of('10", PIPE, 0.365" W.T.') == "piping"
    cols = _columns(["ITEM #", "PRODUCT DESCRIPTION", "MANUFACTURER", "PART NO.", "QTY.", "SUPPLIED", "INSTALLED"])
    assert cols["qty"] == 4 and cols["desc"] == 1


def test_bulk_scope_aliases_and_unknown_quantity():
    assert _scope_reference('8" WELD NECK FLANGE', "Install new flanges") == "flange"
    assert _scope_reference("SPIRAL WOUND GASKET", "Provide gaskets") == "gasket"
    assert _scope_reference("STUD BOLT", "Provide bolting") == "bolting"
    assert _scope_reference("HEX NUT", "Provide bolting") == "bolting"
    assert _scope_reference("CARBON STEEL PIPE", "Install new pipe") == "pipe"
    assert _scope_reference("BALL VALVE", "Replace valves") == "valve"
    assert not _scope_reference("PIPE SUPPORT", "Provide bolting")
    assert _qty("AS REQ.") == (None, "", "")


def test_custom_scope_alias(monkeypatch):
    from app.services import embedded_bom
    monkeypatch.setitem(embedded_bom.VOCAB["scope_aliases"], "jointing", {"GASKET"})
    assert _scope_reference("SPIRAL WOUND GASKET", "Install jointing") == "jointing"


def test_missing_ocr_is_reported(tmp_path, monkeypatch):
    from app.services import drawing_ocr
    image = Image.new("RGB", (400, 200), "white")
    path = tmp_path / "image.pdf"
    c = canvas.Canvas(str(path), pagesize=(400, 200))
    c.drawImage(ImageReader(image), 0, 0)
    c.showPage()
    c.save()
    monkeypatch.setattr(drawing_ocr.shutil, "which", lambda _: None)
    result = build_scoped_bom(str(path), output_dir=str(tmp_path))
    assert result["status"] == "needs_clarification"
    assert any(q["type"] == "ocr_unavailable" for q in result["questions"])


def test_packaged_ocr_prefers_bundled_runtime(tmp_path, monkeypatch):
    import sys
    from app.services import drawing_ocr

    root = tmp_path / "tesseract"
    root.mkdir()
    exe = root / ("tesseract.exe" if sys.platform.startswith("win") else "tesseract")
    exe.write_text("test")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    binary, env = drawing_ocr._tesseract()
    assert binary == str(exe) and env["TESSDATA_PREFIX"] == str(root / "tessdata")


def test_ai_fallback_when_tesseract_is_unavailable(tmp_path, monkeypatch):
    from app.services import ai_review, drawing_ocr
    image = Image.new("RGB", (400, 200), "white")
    path = tmp_path / "image.pdf"
    c = canvas.Canvas(str(path), pagesize=(400, 200))
    c.drawImage(ImageReader(image), 0, 0)
    c.showPage()
    c.save()
    monkeypatch.setattr(drawing_ocr.shutil, "which", lambda _: None)
    monkeypatch.setattr(ai_review, "is_enabled", lambda: True)
    monkeypatch.setattr(ai_review, "transcribe_bom_with_ai", lambda path, page: {
        "items": [{"item": "1", "description": "flange", "quantity": 2, "unit": "ea", "notes": ""}],
        "issues": [], "provider": "fake", "model": "fake"})
    result = build_scoped_bom(str(path), output_dir=str(tmp_path))
    assert result["status"] == "completed"
    assert result["materials"][0]["origin"] == "drawing_bom_ai"
    assert any(f["type"] == "ai_bom_transcription" for f in result["flags"])
    from app.services.review_questions import build_questions
    crosscheck = next(q for q in build_questions(result["flags"], result["materials"])
                      if q["flag_type"] == "bom_scope_crosscheck")
    assert crosscheck["locations"][0]["page"] == 1
    assert "x" not in crosscheck["locations"][0]


def test_unreadable_ocr_bom_cannot_fall_back_to_tag_scan(tmp_path, monkeypatch):
    from app.services import drawing_ocr
    image = Image.new("RGB", (400, 200), "white")
    path = tmp_path / "image.pdf"
    c = canvas.Canvas(str(path), pagesize=(400, 200))
    c.drawImage(ImageReader(image), 0, 0)
    c.showPage()
    c.save()
    monkeypatch.setattr(drawing_ocr, "inspect_image_page",
                        lambda page, page_no: ([], [{"type": "ocr_bom", "reconstructed": False,
                                                     "message": "BOM table unreadable"}]))
    result = build_scoped_bom(str(path), new_work_pages=[1], output_dir=str(tmp_path))
    assert result["status"] == "needs_clarification"
    assert any(q["type"] == "ocr_bom_unreadable" for q in result["questions"])


def test_ai_fallback_transcribes_unreadable_bom(tmp_path, monkeypatch):
    from app.services import ai_review, drawing_ocr

    image = Image.new("RGB", (400, 200), "white")
    path = tmp_path / "image.pdf"
    c = canvas.Canvas(str(path), pagesize=(400, 200))
    c.drawImage(ImageReader(image), 0, 0)
    c.showPage()
    c.save()
    monkeypatch.setattr(drawing_ocr, "inspect_image_page",
                        lambda page, page_no: ([], [{"type": "ocr_bom", "page": page_no,
                                                     "reconstructed": False, "message": "BOM unreadable"}]))
    monkeypatch.setattr(ai_review, "is_enabled", lambda: True)

    class FakeProvider(ai_review.Provider):
        name, default_model = "fake", "test"

        def __init__(self):
            super().__init__("unused")
            self.calls = 0

        def generate(self, prompt, images):
            assert images and "page 1" in prompt
            self.calls += 1
            if self.calls == 1:
                return json.dumps({"complete": True, "items": [
                    {"item": "11", "description": "8 inch flange", "quantity": 2, "unit": "ea", "notes": ""},
                    {"item": "12", "description": "stud bolt", "quantity": None, "unit": "", "notes": ""},
                ]})
            return json.dumps({"complete": False, "items": []})

    provider = FakeProvider()
    monkeypatch.setattr(ai_review, "get_provider", lambda: provider)
    result = build_scoped_bom(str(path), scope_text="Install flanges and bolting", output_dir=str(tmp_path))
    assert provider.calls == 2 and result["status"] == "completed"
    rows = {r["tag_id"]: r for r in result["materials"]}
    assert rows["11"]["scope_match"] == "flange" and rows["11"]["quantity"] == 2
    assert rows["12"]["quantity"] is None
    assert all(r["origin"] == "drawing_bom_ai" and "unverified" in r["basis"] for r in rows.values())
    assert result["classification_confidence"] == 0.4
    flag = next(f for f in result["flags"] if f["type"] == "ai_bom_transcription")
    assert "region 2 may be incomplete" in flag["message"] and flag["severity"] == "review"
    assert all(result[key] for key in ("bom_pdf", "bom_json", "bom_csv"))


@pytest.mark.parametrize("reply", [
    "not json",
    '{"complete": true, "items": []}',
    '{"complete": true, "items": [{"item": "11", "description": "flange", "quantity": "many", "unit": "ea"}]}',
])
def test_invalid_ai_bom_response_still_requires_clarification(tmp_path, monkeypatch, reply):
    from app.services import ai_review, drawing_ocr

    image = Image.new("RGB", (400, 200), "white")
    path = tmp_path / "image.pdf"
    c = canvas.Canvas(str(path), pagesize=(400, 200))
    c.drawImage(ImageReader(image), 0, 0)
    c.showPage()
    c.save()
    monkeypatch.setattr(drawing_ocr, "inspect_image_page",
                        lambda page, page_no: ([], [{"type": "ocr_bom", "page": page_no,
                                                     "reconstructed": False, "message": "BOM unreadable"}]))
    monkeypatch.setattr(ai_review, "is_enabled", lambda: True)

    class FakeProvider(ai_review.Provider):
        name, default_model = "fake", "test"
        def generate(self, prompt, images):
            return reply

    monkeypatch.setattr(ai_review, "get_provider", lambda: FakeProvider("unused"))
    result = build_scoped_bom(str(path), new_work_pages=[1], output_dir=str(tmp_path))
    assert result["status"] == "needs_clarification"
    assert any(q["type"] == "ai_bom_failed" for q in result["questions"])
    assert any(q["type"] == "ocr_bom_unreadable" for q in result["questions"])


def test_native_printed_bom_keeps_unmatched_and_unknown_quantities(tmp_path):
    path = tmp_path / "bom.pdf"
    doc = SimpleDocTemplate(str(path))
    table = Table([["ITEM #", "PRODUCT DESCRIPTION", "QTY"],
                   ["11", '8" FLANGE', "2"],
                   ["12", "STUD BOLT", "AS REQ."],
                   ["13", "PIPE SUPPORT", "1"]])
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 1, "black")]))
    doc.build([table])
    result = build_scoped_bom(str(path), scope_text="Install flanges and bolting",
                              output_dir=str(tmp_path))
    rows = {m["tag_id"]: m for m in result["materials"]}
    assert set(rows) == {"11", "12", "13"}
    assert rows["11"]["scope_match"] == "flange" and rows["11"]["quantity"] == 2
    assert rows["12"]["scope_match"] == "bolting" and rows["12"]["quantity"] is None
    assert rows["12"]["notes"] == ""
    assert rows["13"]["scope_match"] == "" and rows["13"]["quantity"] == 1
    assert "No configured scope term" in rows["13"]["scope_match_reason"]
    assert "scope mentions" in rows["11"]["scope_match_reason"].lower()
    assert "BOM term 'FLANGE'" in rows["11"]["scope_match_reason"]
    assert "Install flanges and bolting" in rows["11"]["scope_match_reason"]
    assert all(row["locations"] and row["locations"][0]["page"] == 1 for row in rows.values())
    assert any(f["type"] == "bom_scope_crosscheck" for f in result["flags"])
    flag = next(f for f in result["flags"] if f["type"] == "bom_scope_crosscheck")
    assert "3 of 3 printed BOM rows have descriptions (100% label completeness)" in flag["message"]
    assert "Scope terminology matched 2 of 3" in flag["message"]
    from app.services.review_questions import build_questions
    q = next(q for q in build_questions(result["flags"], result["materials"])
             if q["flag_type"] == "bom_scope_crosscheck")
    assert len(q["locations"]) == 3
    assert "No configured scope term" in q["locations"][2]["review_reason"]
    assert all(result[key] for key in ("bom_pdf", "bom_json", "bom_csv"))


def test_ocr_does_not_guess_a_missing_quantity_column():
    from app.services.drawing_ocr import _table_rows
    words = [{"text": text, "x0": x, "top": y} for text, x, y in
             [("ITEM", 10, 10), ("DESCRIPTION", 100, 10), ("SUPPLIED", 400, 10),
              ("11", 10, 30), ("FLANGE", 100, 30), ("2", 350, 30)]]
    assert _table_rows(words) == []


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract OCR not installed")
def test_image_only_bom_is_ocr_read_and_cross_referenced(tmp_path):
    image = Image.new("RGB", (2400, 1400), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=48)
    draw.text((100, 100), "BILL OF MATERIALS", font=font, fill="black")
    draw.text((1700, 100), "REVISION B", font=font, fill="black")
    for x, text in [(100, "ITEM"), (350, "DESCRIPTION"), (1500, "QTY")]:
        draw.text((x, 250), text, font=font, fill="black")
    for y, item, desc, qty in [(350, "11", "8 INCH FLANGE", "2"),
                               (450, "12", "SPIRAL GASKET", "4"),
                               (550, "13", "STUD BOLT", "AS REQ.")]:
        for x, text in [(100, item), (350, desc), (1500, qty)]:
            draw.text((x, y), text, font=font, fill="black")
    path = tmp_path / "scanned.pdf"
    c = canvas.Canvas(str(path), pagesize=(1200, 700))
    c.drawImage(ImageReader(image), 0, 0, width=1200, height=700)
    c.showPage()
    c.save()

    result = build_scoped_bom(str(path), scope_text="Install flanges and gaskets",
                              output_dir=str(tmp_path))
    assert result["status"] == "completed"
    rows = {m["tag_id"]: m for m in result["materials"]}
    assert set(rows) == {"11", "12", "13"}
    assert rows["11"]["quantity"] == 2 and rows["11"]["scope_match"] == "flange"
    assert rows["12"]["quantity"] == 4 and rows["12"]["scope_match"] == "gasket"
    assert rows["13"]["quantity"] is None and not rows["13"]["scope_match"]
    assert any(f["type"] == "ocr_bom" for f in result["flags"])
    assert any(f["type"] == "ocr_revision" for f in result["flags"])
    assert any(f["type"] == "bom_scope_crosscheck" for f in result["flags"])
