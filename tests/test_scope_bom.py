from __future__ import annotations

import os
from collections import Counter

import pdfplumber
import pytest

from app.services import scope_bom as sb
from tests.conftest import make_pdf


def test_score_freetext():
    assert sb.score_page_by_freetext("DEMO DRAWING")["role"] == "demo"
    assert sb.score_page_by_freetext("NEW INSTALLATION DRAWING")["role"] == "new_work"
    assert sb.score_page_by_freetext("nothing")["role"] is None


def test_score_title():
    assert sb.score_page_by_title("Demolition plan")["role"] == "demo"
    assert sb.score_page_by_title("Proposed layout")["role"] == "new_work"


def test_parse_legend_and_key():
    legend = sb.parse_legend("TK - Storage Tank\nJFSP = Fuel Pump   POV - Pilot Valve")
    assert legend["TK"] == "Storage Tank"
    assert legend["JFSP"] == "Fuel Pump"
    assert legend["POV"] == "Pilot Valve"
    key = sb.parse_instrument_key("X - Custom Variable")
    assert key["first_letters"]["X"] == "Custom Variable"
    assert key["first_letters"]["P"] == "Pressure"


def test_describe_tag_sources():
    legend = {"abbreviations": {"TK": "Storage Tank"}, "instrument_key": sb.parse_instrument_key("")}
    assert sb.describe_tag("TK-1", legend)["source"] == "legend"
    assert sb.describe_tag("PI-2", {"abbreviations": {}})["source"] == "prefix_map"
    assert sb.describe_tag("PAH-2", legend)["description"] == "Pressure Alarm High"
    assert sb.describe_tag("ZZZ-1", legend)["source"] == "default"


def _sig(page, tags=(), words=(), colours=None, **kw):
    return {"page": page, "tags": set(tags), "words": set(words), "colours": Counter(colours or {}),
            "freetext": "", "title_text": "", "text": "", **kw}


def test_pairs_and_classify_by_jaccard():
    sigs = [
        _sig(1, ["A-1"], ["LEGEND"]),
        _sig(2, ["TK-1", "PI-1"], freetext="DEMO DRAWING"),
        _sig(3, ["TK-1", "PI-1", "PV-2"]),
    ]
    assert sb.find_page_pairs_by_content(sigs)[0][:2] == (2, 3)
    result = sb.classify_signatures(sigs)
    assert result["demo_pages"] == [2] and result["new_work_pages"] == [3]
    assert result["classification_method"] == "freetext"


def test_colour_tiebreak_and_ambiguity():
    red, green = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
    sigs = [_sig(1, ["TK-1"], colours={red: 5}), _sig(2, ["TK-1"], colours={green: 5})]
    assert sb.classify_signatures(sigs)["ambiguous"]
    mapped = sb.classify_signatures(sigs, {"red": "demo", "green": "new_work"})
    assert mapped["demo_pages"] == [1] and mapped["new_work_pages"] == [2]
    assert mapped["classification_method"] == "colour_tiebreak"


def test_detect_colour_meaning():
    red, green = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
    scheme = sb.detect_colour_meaning([_sig(1, colours={red: 4})], [_sig(2, colours={green: 4})])
    assert scheme["[1,0,0]"]["meaning"] == "demo"
    assert scheme["[0,1,0]"]["meaning"] == "new_work"


def test_cross_check_scope():
    desc = {"TK-1": {"description": "Storage Tank"}, "PI-2": {"description": "Pressure Indicator"}}
    flags = sb.cross_check_scope("Replace TK-1 and install POV-9. Add a filter.", ["TK-1", "PI-2"], desc)
    types = {(f["type"], f.get("tag") or f.get("item")) for f in flags}
    assert ("scope_tag_not_found", "POV-9") in types
    assert ("scope_item_without_tag", "filter") in types
    assert ("tag_not_in_scope", "PI-2") in types
    assert not any(f.get("tag") == "TK-1" for f in flags)
    assert sb.cross_check_scope("", [], {})[0]["type"] == "no_scope_text"


def test_signature_and_classify_pages(freetext_pdf):
    with pdfplumber.open(freetext_pdf) as pdf:
        sig = sb.extract_page_content_signature(pdf, 2)
        assert "TK-1" in sig["tags"] and "DEMO DRAWING" in sig["freetext"]
        assert (1.0, 0.0, 0.0) in sig["colours"]
        result = sb.classify_pages_by_content(pdf)
    assert result["demo_pages"] == [2] and result["new_work_pages"] == [3]


def test_find_legend_page(freetext_pdf):
    with pdfplumber.open(freetext_pdf) as pdf:
        assert sb.find_legend_page(pdf) == 1


def test_build_scoped_bom_completed(freetext_pdf, tmp_path):
    result = sb.build_scoped_bom(freetext_pdf, scope_text="Job#26-117 Replace TK-1, JFSP-1, POV-1, PI-2",
                                 output_dir=str(tmp_path))
    assert result["status"] == "completed"
    assert result["job_number"] == "Job#26-117"
    assert result["demo_pages"] == [2] and result["new_work_pages"] == [3]
    assert result["classification_method"] == "freetext"
    assert result["legend"]["found"] and result["legend"]["entries_found"] == 3
    assert result["colour_scheme"]["[1,0,0]"]["meaning"] == "demo"
    assert {m["tag_id"] for m in result["materials"]} == {"TK-1", "JFSP-1", "POV-1", "PI-2"}
    assert next(m for m in result["materials"] if m["tag_id"] == "TK-1")["description"] == "Storage Tank"
    assert os.path.exists(result["bom_pdf"])


def test_build_scoped_bom_clarification_and_override(ambiguous_pdf, tmp_path):
    result = sb.build_scoped_bom(ambiguous_pdf, output_dir=str(tmp_path))
    assert result["status"] == "needs_clarification"
    q = result["questions"][0]
    assert q["type"] == "demo_work_pages_ambiguous"
    assert q["candidate_pairs"][0]["pages"] == [2, 3]

    by_pages = sb.build_scoped_bom(ambiguous_pdf, demo_pages=[2], new_work_pages=[3], output_dir=str(tmp_path))
    assert by_pages["status"] == "completed"
    assert by_pages["classification_method"] == "user_override"
    assert by_pages["classification_confidence"] == 1.0

    by_colour = sb.build_scoped_bom(ambiguous_pdf, highlight_mapping={"red": "demo", "green": "new_work"},
                                    output_dir=str(tmp_path))
    assert by_colour["status"] == "completed" and by_colour["new_work_pages"] == [3]


def test_no_legend_flagged(tmp_path):
    path = make_pdf(tmp_path / "x.pdf", [(["TK-1"], (0, 0, 0))])
    result = sb.build_scoped_bom(path, new_work_pages=[1], output_dir=str(tmp_path))
    assert result["status"] == "completed"
    assert any(f["type"] == "legend_not_parsed" for f in result["flags"])


REAL_DIR = "backend/uploads"


@pytest.mark.skipif(not os.path.isdir(REAL_DIR), reason="backend/uploads not available")
def test_real_file_smoke(tmp_path):
    pdfs = [f for f in os.listdir(REAL_DIR) if f.lower().endswith(".pdf")]
    if not pdfs:
        pytest.skip("no PDFs in backend/uploads")
    result = sb.build_scoped_bom(os.path.join(REAL_DIR, pdfs[0]), output_dir=str(tmp_path))
    assert result["status"] in ("completed", "needs_clarification")
