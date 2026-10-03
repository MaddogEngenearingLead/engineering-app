import pymupdf
import pytest

from app.services.scope_bom import (
    describe_tag, detect_highlights, detect_legend, load_pid, run_scope_bom,
)

LEGEND = """MECHANICAL LEGEND AND ABBREVIATIONS
INSTRUMENT IDENTIFICATION KEY
AE   BULK AIR ELIMINATOR
LPD   LOW POINT DRAIN
HPV   HIGH POINT VENT
TK   TANK
POV   PNEUMATIC OPERATED VALVE
JFSP   CENTRIFUGAL PUMP
PRV   PRESSURE RELIEF VALVE
FIRST LETTER
P   PRESSURE
L   LEVEL
T   TEMPERATURE
SUCCEEDING LETTERS
I   INDICATOR
S   SWITCH
H   HIGH
NEW WORK
DEMOLITION"""

SCOPE = """Install tank 1 with a manway.
Provide 2 in ball valve at the pump.
Install DBB valves.
Replace the filter separator."""


def _mark(page, text, point, color, kind="highlight"):
    page.insert_text(point, text, fontsize=10)
    rect = page.search_for(text)[0]
    annot = page.add_highlight_annot(rect) if kind == "highlight" else page.add_circle_annot(rect)
    annot.set_colors(stroke=color)
    annot.update()


@pytest.fixture
def pages(tmp_path):
    doc = pymupdf.open()
    legend = doc.new_page(width=612, height=792)
    legend.insert_textbox(pymupdf.Rect(20, 20, 580, 780), LEGEND, fontsize=8)

    demo = doc.new_page(width=612, height=792)
    demo.insert_text((20, 30), "DEMO DRAWING EQUIPMENT PAD", fontsize=10)
    _mark(demo, "TK-1", (100, 200), (1, 0, 0))
    _mark(demo, "N2", (100, 250), (1, 0, 0))
    demo.add_freetext_annot(pymupdf.Rect(300, 300, 500, 340),
                            "ALL BOLD PIPING AND EQUIPMENT IS DEMO SCOPE")

    new = doc.new_page(width=612, height=792)
    new.insert_text((20, 30), "NEW INSTALLATION DRAWING EQUIPMENT PAD", fontsize=10)
    _mark(new, "TK-1", (100, 200), (0, 1, 0))
    _mark(new, "LPD-3", (100, 250), (0, 1, 0))
    _mark(new, "POV-1", (100, 300), (0, 1, 0))
    _mark(new, "M-601", (100, 350), (0, 1, 0))
    _mark(new, "HPV-2", (100, 400), (1, 0, 0), kind="circle")
    new.add_freetext_annot(pymupdf.Rect(300, 500, 500, 540), "REINSTALL EXISTING GAUGE")

    path = tmp_path / "pid.pdf"
    doc.save(path)
    return load_pid(str(path))


def test_legend_auto_detected(pages):
    legend = detect_legend(pages)
    assert legend["legend_page"] == 1 and not legend["ask_user"]
    assert legend["abbreviations"]["LPD"] == "Low Point Drain"
    assert legend["first_letters"]["P"] == "Pressure"
    assert legend["succeeding_letters"]["S"] == "Switch"
    assert describe_tag("POV-1", legend)["description"] == "Pneumatic Operated Valve - 1"
    assert describe_tag("PI-4", legend)["match"] == "decoded"
    assert describe_tag("LSH-4", legend)["description"] == "Level Switch High - 4"
    assert describe_tag("ZZZ-1", legend)["match"] == "fallback"


def test_legend_clarification_and_override(pages):
    for page in pages:
        page["text"] = "nothing"
    result = run_scope_bom(pages, SCOPE)
    assert result["status"] == "needs_clarification"
    assert result["ask_user"][0]["issue"] == "legend_page_not_identified"
    assert result["ask_user"][0]["candidates"]


def test_highlights_roles_and_pairs(pages):
    legend = detect_legend(pages)
    hl = detect_highlights(pages, legend["legend_page"])
    assert hl["page_roles"] == {1: "reference", 2: "demo", 3: "new"}
    assert hl["pairs"] == [[2, 3]]
    assert not hl["ask_user"]


def test_out_of_scheme_colour_flagged_and_resolved(pages):
    new_page = pages[2]
    new_page["annots"].append({"type": "Highlight", "color": (1, 1, 0),
                            "rect": (95, 190, 130, 205), "content": ""})
    result = run_scope_bom(pages, SCOPE)
    assert result["status"] == "needs_clarification"
    ask = [a for a in result["ask_user"] if a["issue"] == "out_of_scheme_colours"][0]
    assert ask["items"][0]["colour"] == "yellow" and ask["items"][0]["page"] == 3
    assert result["detected_highlights"]
    resolved = run_scope_bom(pages, SCOPE, highlight_mapping={"colours": {"yellow": "ignore"}})
    assert resolved["status"] == "completed"


def test_scope_cross_check(pages):
    result = run_scope_bom(pages, SCOPE)
    assert result["status"] == "completed"
    tags = {m["tag_id"]: m for m in result["materials"]}
    # N2 / M-601 are not tags; red circle on the new-work page is ignored
    assert set(tags) == {"TK-1", "LPD-3", "POV-1", "-"}
    assert tags["-"]["type"] == "fallback" and tags["-"]["confidence"] < 0.3
    assert tags["POV-1"]["description"] == "Pneumatic Operated Valve - 1"
    assert any(n.startswith('matches scope text: "Install tank 1') for n in tags["TK-1"]["notes"])
    assert "replaces demolished TK-1 on page 2" in tags["TK-1"]["notes"]
    assert "P&ID item not in scope" in tags["LPD-3"]["notes"]
    missing = {i["term"] for i in result["scope_items_not_on_pid"]}
    assert {"ball valve", "filter separator", "manway", "dbb valve"} <= missing
    assert any("REINSTALL EXISTING GAUGE" in f["text"] for f in result["flags"])


def test_endpoint(pages, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app

    doc = pymupdf.open()
    doc.new_page().insert_text((20, 30), "blank")
    pdf = doc.tobytes()
    client = TestClient(app)
    response = client.post(
        "/api/scope-bom",
        files={"pid_file": ("a.pdf", pdf, "application/pdf"),
               "scope_file": ("s.txt", SCOPE.encode(), "text/plain")},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "needs_clarification"
    bad = client.post(
        "/api/scope-bom",
        files={"pid_file": ("a.pdf", pdf, "application/pdf"),
               "scope_file": ("s.txt", b"x", "text/plain")},
        data={"highlight_mapping": "{bad"},
    )
    assert bad.status_code == 400
