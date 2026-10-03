from __future__ import annotations

import pytest

from app.services.scope_bom import (
    build_scoped_bom,
    classify_pages_by_content,
    classify_signatures,
    detect_colour_meaning,
    extract_page_content_signature,
    find_page_pairs_by_content,
    score_page_by_freetext,
    score_page_by_title,
)
from tests.pdf_helpers import build_pdf

TAGS = ["MOV-001", "TK-1", "JFSP-1", "PI-10", "TI-11"]


def sig(tags, text="", notes=None, colours=None):
    return {"tags": set(tags), "tag_count": len(tags), "colours": colours or [],
            "text": text, "freetext_notes": notes or []}


def test_freetext_scoring():
    d = score_page_by_freetext("DEMO DRAWING")
    n = score_page_by_freetext("NEW INSTALLATION DRAWING")
    assert d["method"] == "freetext" and d["demo"] >= 0.8 and d["new_work"] == 0
    assert n["new_work"] >= 0.8 and n["demo"] == 0
    assert score_page_by_freetext("ALL BOLD PIPING AND EQUIPMENT IS DEMO SCOPE")["demo"] >= 0.8
    assert score_page_by_freetext("ALL BOLD PIPING AND EQUIPMENT IS IN SCOPE")["new_work"] >= 0.8
    assert score_page_by_freetext("nothing here") == {"demo": 0.0, "new_work": 0.0, "method": "freetext"}


def test_freetext_classification():
    result = classify_signatures({
        2: sig(TAGS, notes=["DEMO DRAWING"]),
        4: sig(TAGS[:4], notes=["NEW INSTALLATION DRAWING"]),
    })
    assert result["demo_pages"] == [2] and result["new_work_pages"] == [4]
    assert result["method"] == "freetext" and result["confidence"] >= 0.8


def test_title_scoring_and_matching():
    assert score_page_by_title("EQUIPMENT PAD (DEMO)")["demo"] >= 0.8
    assert score_page_by_title("EQUIPMENT PAD (NEW)")["new_work"] >= 0.8
    result = classify_signatures({
        2: sig([], text="EQUIPMENT PAD (DEMO)"),
        4: sig([], text="EQUIPMENT PAD (NEW)"),
    })
    assert result["demo_pages"] == [2] and result["new_work_pages"] == [4]
    assert result["method"] == "title"
    # Unlabelled page with same title key is the opposite state
    result = classify_signatures({
        2: sig([], text="FUEL ROOM (DEMO)"),
        3: sig([], text="FUEL ROOM"),
    })
    assert result["new_work_pages"] == []  # unlabelled title has no key; nothing to pair


def test_content_signature_and_pairing(tmp_path):
    pdf = build_pdf(tmp_path / "a.pdf", [
        {"lines": ["MOV-001", "TK-1", "JFSP-1", "PI-10"]},
        {"lines": ["MOV-001", "TK-1", "JFSP-1", "TI-11"]},
        {"lines": ["LS-5"]},
    ])
    s = extract_page_content_signature(pdf, 1)
    assert s["tags"] == {"MOV-001", "TK-1", "JFSP-1", "PI-10"} and s["tag_count"] == 4
    sigs = {n: extract_page_content_signature(pdf, n) for n in (1, 2, 3)}
    pairs = find_page_pairs_by_content(pdf, sigs)
    assert len(pairs) == 1
    a, b, sim, overlap = pairs[0]
    assert (a, b) == (1, 2) and sim == pytest.approx(3 / 5)
    assert overlap == ["JFSP-1", "MOV-001", "TK-1"]


def test_ambiguous_pages_request_clarification(tmp_path):
    pdf = build_pdf(tmp_path / "amb.pdf", [
        {"lines": ["MOV-001", "TK-1", "JFSP-1", "PI-10"]},
        {"lines": ["MOV-001", "TK-1", "JFSP-1", "TI-11"]},
    ])
    result = build_scoped_bom(pdf, "")
    assert result["status"] == "needs_clarification"
    assert result["question"] == "demo_work_pages"
    pair = result["candidate_pairs"][0]
    assert pair["pages"] == [1, 2]
    assert pair["differences"] == {"added": ["TI-11"], "removed": ["PI-10"],
                                   "unchanged": ["JFSP-1", "MOV-001", "TK-1"]}
    assert "demolition" in result["prompt"]


def test_colour_tiebreak_resolves_pair():
    result = classify_signatures({
        1: sig(TAGS, colours=["[1.0,0.0,0.0]"] * 3),
        2: sig(TAGS, colours=["[0.0,1.0,0.0]"] * 3),
    })
    assert result["demo_pages"] == [1] and result["new_work_pages"] == [2]
    assert result["method"] == "content_match+colour" and result["ambiguous_pairs"] == []


def test_colour_detection_given_pages(tmp_path):
    pdf = build_pdf(tmp_path / "c.pdf", [
        {"lines": ["MOV-001", "TK-1"], "highlights": [(0, "ff0000"), (1, "ff0000")]},
        {"lines": ["MOV-001", "TK-1"], "highlights": [(0, "00ff00"), (1, "00ff00")]},
    ])
    result = detect_colour_meaning(pdf, [1], [2])
    meanings = result["colour_meanings"]
    assert meanings["[1.0,0.0,0.0]"]["meaning"] == "demo"
    assert meanings["[0.0,1.0,0.0]"]["meaning"] == "new_work"
    assert meanings["[0.0,1.0,0.0]"]["confidence"] >= 0.8 and result["known"]


def test_full_flow_with_freetext_and_colour(tmp_path):
    pdf = build_pdf(tmp_path / "f.pdf", [
        {"lines": ["LEGEND", "ABBREVIATION KEY", "TK - TANK"]},
        {"lines": ["MOV-001", "TK-1"], "freetext": ["DEMO DRAWING"], "highlights": [(0, "ff0000"), (1, "ff0000")]},
        {"lines": ["MOV-001", "JFSP-1"], "freetext": ["NEW INSTALLATION DRAWING"],
         "highlights": [(0, "00ff00"), (1, "00ff00")]},
    ])
    result = build_scoped_bom(pdf, "Install new pump JFSP-1")
    assert result["status"] == "ok"
    assert (result["demo_pages"], result["new_work_pages"]) == ([2], [3])
    assert result["classification_method"] == "freetext"
    assert result["content_differences"]["added"] == ["JFSP-1"]
    assert result["content_differences"]["removed"] == ["TK-1"]
    assert result["colour_filtering_applied"] is True
    assert {m["tag_id"] for m in result["materials"]} == {"MOV-001", "JFSP-1"}
    assert result["legend"]["found"] and result["legend"]["page"] == 1
    assert all({"pages", "classification_method", "classification_confidence"} <= f.keys()
               for f in result["flags"])


def test_colour_unknown_includes_all_items_flagged(tmp_path):
    pdf = build_pdf(tmp_path / "n.pdf", [
        {"lines": ["TK-1"], "freetext": ["DEMO DRAWING"]},
        {"lines": ["MOV-001", "JFSP-1"], "freetext": ["NEW WORK"]},
    ])
    result = build_scoped_bom(pdf, "")
    assert result["status"] == "ok" and result["colour_filtering_applied"] is False
    assert {m["tag_id"] for m in result["materials"]} == {"MOV-001", "JFSP-1"}
    assert sum(f["type"] == "colour_unknown" for f in result["flags"]) == 2


def test_user_override_and_highlight_mapping(tmp_path):
    pdf = build_pdf(tmp_path / "u.pdf", [
        {"lines": ["MOV-001", "TK-1", "JFSP-1", "PI-10"]},
        {"lines": ["MOV-001", "TK-1", "JFSP-1", "TI-11"], "highlights": [(3, "00ff00"), (0, "ff0000")]},
    ])
    mapping = {"[0.0,1.0,0.0]": "new_work", "[1.0,0.0,0.0]": "demo"}
    result = build_scoped_bom(pdf, "", demo_pages=[1], new_work_pages=[2], highlight_mapping=mapping)
    assert result["status"] == "ok" and result["classification_method"] == "user_input"
    ids = {m["tag_id"] for m in result["materials"]}
    assert "TI-11" in ids and "MOV-001" not in ids
    assert build_scoped_bom(pdf, "", demo_pages=[1], new_work_pages=[9])["status"] == "needs_clarification"


def test_classify_pages_by_content_returns_signatures(tmp_path):
    pdf = build_pdf(tmp_path / "s.pdf", [{"lines": ["TK-1"], "freetext": ["DEMO DRAWING"]}])
    result = classify_pages_by_content(pdf)
    assert result["demo_pages"] == [1] and 1 in result["signatures"]
