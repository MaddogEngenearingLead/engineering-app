import pytest

from app.services.pid_markup import _pipe_labels, markup_items
from app.services.pid_scope import scope_items
from app.services.review_questions import apply_answer, build_questions, undo_answer
from app.services.size_labels import sizes_in


@pytest.mark.parametrize("text,expected", [
    ('Install new 1/4" check valve.', '1/4" Check Valve'),
    ('Install new 1-1/4" check valve.', '1-1/4" Check Valve'),
    ('Install new 6"x4" fire valve.', '6"x4" Fire Valve'),
    ('Install new 6" × 4" fire valve.', '6"x4" Fire Valve'),
    ('Install new ½" check valve.', '½" Check Valve'),
])
def test_scope_component_sizes_are_not_truncated(text, expected):
    assert [row["description"] for row in scope_items(text)] == [expected]


def test_invalid_partial_fraction_is_not_interpreted_as_whole_size():
    assert sizes_in('/4"') == []
    assert sizes_in('1/4"') == ['1/4"']


def test_pipe_label_keeps_fraction_and_requires_material():
    words = [
        {"text": '1/4"', "x0": 0, "x1": 10, "top": 0, "bottom": 4},
        {"text": "CS", "x0": 12, "x1": 20, "top": 0, "bottom": 4},
    ]
    assert _pipe_labels(words)[0]["spec"] == '1/4" CS'
    assert not _pipe_labels(words[:1])


def test_markup_location_is_on_real_segment(monkeypatch):
    from app.services import pid_markup, pid_labels
    class Page:
        width, height, annots = 1000, 1000, []
        def extract_words(self): return []
        def extract_text_lines(self): return []
    monkeypatch.setattr(pid_labels, "grid_locator", lambda page: lambda x, y: "")
    monkeypatch.setattr(pid_markup, "_segments", lambda page, colours: [(10, 10, 90, 10), (90, 10, 90, 80)])
    result = markup_items(Page(), set())
    assert (result["pipes"][0]["x"], result["pipes"][0]["y"]) == (50, 10)


def test_unclassified_markup_can_be_reviewed_and_added_without_guessing_quantity():
    flag = {"type": "unclassified_markup", "severity": "review", "page": 2,
            "locations": [{"page": 2, "x": 40, "y": 50, "grid": ""}],
            "message": "Highlighted line needs identification."}
    q = build_questions([flag], [])[0]
    assert q["locations"][0]["x"] == 40
    rows = []
    with pytest.raises(ValueError, match="description"):
        apply_answer(rows, q, {"choice": "add", "fields": {}})
    with pytest.raises(ValueError, match="quantity"):
        apply_answer(rows, q, {"choice": "add", "fields": {"description": "Valve", "qty": "nan"}})
    answer = {"choice": "add", "fields": {"description": '6"x4" Fire Valve', "qty": "", "unit": ""}}
    record = apply_answer(rows, q, answer)
    assert rows[0]["description"] == '6"x4" Fire Valve'
    assert rows[0]["quantity"] is None and rows[0]["type"] == "user_identified"
    assert rows[0]["locations"][0]["x"] == 40
    undo_answer(rows, record)
    assert not rows
