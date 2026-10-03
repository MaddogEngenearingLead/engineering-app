import pytest
from reportlab.pdfgen import canvas

from app.services.bom_export import export_bom_to_pdf
from app.services.scope_bom import (
    build_scoped_bom,
    classify_color,
    extract_job_number,
    extract_legend,
    find_scope_document,
)


def make_pid(path):
    c = canvas.Canvas(str(path), pagesize=(800, 600))
    c.drawString(50, 550, "MECHANICAL LEGEND")
    c.drawString(50, 530, "TK-1   STORAGE TANK")
    c.drawString(50, 510, "JFSP-1   CENTRIFUGAL PUMP")
    c.drawString(50, 490, "POV - PNEUMATIC OPERATED VALVE")
    c.showPage()
    c.showPage()
    c.showPage()
    # page 4
    c.drawString(100, 500, "POV-1")
    c.drawString(300, 500, "TK-1")
    c.drawString(500, 500, "JFSP-1")
    c.setLineWidth(2)
    c.setStrokeColorRGB(0, 1, 0)
    c.rect(95, 495, 50, 18)
    c.rect(495, 495, 60, 18)
    c.rect(100, 300, 40, 40)  # untagged green
    c.setStrokeColorRGB(1, 0, 0)
    c.rect(295, 495, 50, 18)  # red tag
    c.setStrokeColorRGB(1, 1, 0)
    c.rect(600, 300, 30, 30)  # yellow
    c.drawString(105, 280, "SPARE")
    c.showPage()
    c.showPage()
    c.save()


def test_helpers(tmp_path):
    assert extract_job_number("Job#26-117 Scope-Work Plan (1).docx") == "Job#26-117"
    assert extract_job_number("other.docx") is None
    assert classify_color((0, 1, 0)) == "green"
    assert classify_color((1, 0, 0)) == "red"
    assert classify_color([0, 0, 1]) == "blue"
    assert classify_color((0, 0, 0)) is None
    assert classify_color((1, 1, 0)) == "other"
    (tmp_path / "Job#26-117 Scope.docx").write_text("x")
    (tmp_path / "~$Job.docx").write_text("x")
    assert find_scope_document(tmp_path).name == "Job#26-117 Scope.docx"
    assert find_scope_document(tmp_path / "missing") is None
    legend = extract_legend("TK-1   STORAGE TANK\nPOV - PNEUMATIC OPERATED VALVE")
    assert legend["TK-1"] == "Storage Tank"
    assert legend["POV"] == "Pneumatic Operated Valve"


def test_scoped_bom(tmp_path):
    pdf = tmp_path / "pid.pdf"
    make_pid(pdf)
    result = build_scoped_bom(str(pdf))
    tags = {m["tag_id"]: m["description"] for m in result["materials"]}
    assert tags == {"JFSP-1": "Centrifugal Pump", "POV-1": "Pneumatic Operated Valve"}
    assert len(result["flags"]["untagged_green"]) == 1
    assert "SPARE" in result["flags"]["untagged_green"][0]["nearby_text"]
    assert any("yellow" in m["color"] for m in result["flags"]["mixed_colors"])

    out = export_bom_to_pdf(
        "Job#26-117", "pid.pdf", result["materials"],
        output_dir=str(tmp_path), flags=result["flags"],
    )
    assert "BOM_Job#26-117_" in out
