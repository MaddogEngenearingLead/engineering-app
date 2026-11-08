import os
import tkinter as tk

import pytest
from PIL import Image

from app.gui.review_window import LocationViewer, ReviewWindow
from app.services.review_questions import build_questions


def _questions():
    items = [
        {"tag": "V-1", "description": "Valve", "reason": "Not in scope",
         "locations": [{"page": 1, "x": 100, "y": 120, "grid": "A1"}]},
        {"tag": "P-2", "description": "Pump", "reason": "Existing equipment",
         "locations": [{"page": 2, "x": 180, "y": 160, "grid": "B2"}]},
    ]
    return build_questions([{"type": "ai_missing_items", "items": items, "message": "AI review"}], [])


def test_question_locations_keep_item_and_reason_without_mutation():
    q = _questions()[0]
    assert [loc["review_item"] for loc in q["locations"]] == ["V-1 - Valve", "P-2 - Pump"]
    assert [loc["review_reason"] for loc in q["locations"]] == ["Not in scope", "Existing equipment"]
    assert "review_item" not in q["items"][0]["locations"][0]


def test_unknown_tag_multiple_locations_and_old_flags():
    flag = {"type": "unidentified_tags", "tags": ["ZZQ-7", "ABQ-123"],
            "message": "unknown tags", "locations": [
                {"tag": "ZZQ-7", "page": 2, "x": 20, "y": 30, "grid": ""},
                {"tag": "ABQ-123", "page": 2, "x": 50, "y": 60, "grid": ""},
                {"tag": "ZZQ-7", "page": 3, "x": 70, "y": 80, "grid": ""},
            ]}
    q = build_questions([flag], [])[0]
    assert [loc["review_item"] for loc in q["locations"]] == ["ZZQ-7", "ABQ-123", "ZZQ-7"]
    assert not build_questions([{k: v for k, v in flag.items() if k != "locations"}], [])[0]["locations"]


def test_generic_warnings_use_available_locations_and_never_guess():
    flags = [
        {"type": "another_warning", "severity": "warning", "page": 17, "message": "Page issue"},
        {"type": "another_warning", "severity": "warning", "page": 18, "x": 20, "y": 30, "message": "Spot"},
        {"type": "tag_not_in_scope", "severity": "warning", "tag": "V-2", "message": "Tag"},
        {"type": "scope_tag_not_found", "severity": "warning", "tag": "V-3", "message": "Not found"},
        {"type": "ambiguous", "severity": "review", "pages": [2, 4], "message": "Unclear pages"},
    ]
    materials = [{"tag_id": "V-2", "description": "Valve", "locations": [{"page": 5, "x": 10, "y": 12}]}]
    questions = build_questions(flags, materials)
    assert questions[0]["locations"] == [{"page": 17}]
    assert questions[1]["locations"][0]["x"] == 20
    assert questions[2]["locations"][0]["page"] == 5
    assert questions[3]["locations"] == []
    assert questions[4]["locations"] == [{"page": 2}, {"page": 4}]


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="Tk requires a display")
def test_question_viewer_note_tracks_location_and_zoom(monkeypatch):
    root = tk.Tk()
    root.withdraw()
    monkeypatch.setattr(LocationViewer, "_page_image",
                        lambda self, page: (Image.new("RGB", (1800, 1200), "white"), 600.0, 400.0))
    q = _questions()[0]
    try:
        # Exercise the same entry point as the question dialog.
        owner = type("Owner", (), {"pid_file": "unused.pdf"})()
        viewer = ReviewWindow._show_question(owner, q, root)
        root.update()
        text = viewer.note_text.get("1.0", "end")
        assert "V-1 - Valve" in text and "Not in scope" in text
        assert q["why"] in text and "What:" in text
        viewer.step(1)
        viewer.set_zoom(2)
        root.update()
        text = viewer.note_text.get("1.0", "end")
        assert "P-2 - Pump" in text and "Existing equipment" in text
        assert "V-1 - Valve" not in text
        assert viewer.canvas.find_withtag("all")
        assert viewer.note_text.cget("state") == "disabled"
        viewer.destroy()
    finally:
        root.destroy()


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="Tk requires a display")
def test_note_can_be_dragged_and_keeps_position_while_view_changes(monkeypatch):
    root = tk.Tk()
    root.withdraw()
    monkeypatch.setattr(LocationViewer, "_page_image",
                        lambda self, page: (Image.new("RGB", (1800, 1200), "white"), 600.0, 400.0))
    q = _questions()[0]
    try:
        viewer = LocationViewer(root, "unused.pdf", "Review", q["locations"], question=q)
        root.update()
        start = viewer.note_position
        viewer.note_handle.event_generate("<ButtonPress-1>", x=10, y=8, rootx=100, rooty=100)
        viewer.note_handle.event_generate("<B1-Motion>", x=20, y=18, rootx=200, rooty=150)
        viewer.note_handle.event_generate("<ButtonRelease-1>", x=20, y=18, rootx=200, rooty=150)
        moved = viewer.note_position
        assert moved != start
        assert tuple(viewer.canvas.coords("review_note")) == moved
        assert viewer.canvas.find_withtag("review_note_line")
        assert viewer.pan_x == 0 and viewer.pan_y == 0
        viewer.set_zoom(2)
        assert viewer.note_position == moved
        viewer.step(1)
        assert viewer.note_position == moved
        assert "P-2 - Pump" in viewer.note_text.get("1.0", "end")
        viewer.toggle_note()
        viewer.toggle_note()
        assert viewer.note_position == moved
        viewer.destroy()
    finally:
        root.destroy()


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="Tk requires a display")
def test_user_mark_converts_zoomed_canvas_click_to_drawing_coordinates(monkeypatch):
    root = tk.Tk()
    root.withdraw()
    monkeypatch.setattr(LocationViewer, "_page_image",
                        lambda self, page: (Image.new("RGB", (1800, 1200), "white"), 600.0, 400.0))
    marks = []
    try:
        viewer = LocationViewer(root, "unused.pdf", "Mark", [], page=4, on_mark=marks.append)
        viewer.set_zoom(2)
        left, top, width, height = viewer._view_bounds
        viewer._enable_mark()
        viewer._start_drag(type("Event", (), {"x": 450, "y": viewer._view_height // 2})())
        assert marks[0]["page"] == 4 and marks[0]["location_source"] == "user"
        assert marks[0]["x"] == pytest.approx(left + width / 2, abs=0.1)
        assert marks[0]["y"] == pytest.approx(top + height / 2, abs=1)
        assert not viewer.winfo_exists()
    finally:
        root.destroy()


def test_unknown_split_tag_coordinates(tmp_path):
    import pdfplumber
    from app.services.pid_labels import scan_page_labels
    from tests.conftest import make_pdf

    pdf = make_pdf(tmp_path / "unknown.pdf", [(["ZZQ-7", "XYQ 123", "ZZQ-7"], (0, 0, 0))])
    with pdfplumber.open(pdf) as doc:
        result = scan_page_labels(doc.pages[0], allowed_prefixes=set(), label_codes=set(),
                                  decode_ok=lambda _: False, new_colours=set(), segments=[])
    assert result["unrecognised"] == ["XYQ-123", "ZZQ-7"]
    assert [loc["tag"] for loc in result["unrecognised_locations"]] == ["ZZQ-7", "XYQ-123", "ZZQ-7"]
    assert result["unrecognised_locations"][0]["y"] < result["unrecognised_locations"][2]["y"]


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="Tk requires a display")
def test_unknown_question_opens_each_drawing_location(monkeypatch):
    root = tk.Tk()
    root.withdraw()
    monkeypatch.setattr(LocationViewer, "_page_image",
                        lambda self, page: (Image.new("RGB", (1800, 1200), "white"), 600.0, 400.0))
    flag = {"type": "unidentified_tags", "tags": ["ZZQ-7", "ABQ-123"], "message": "unknown tags",
            "locations": [{"tag": "ZZQ-7", "page": 2, "x": 20, "y": 30},
                          {"tag": "ABQ-123", "page": 3, "x": 50, "y": 60}]}
    q = build_questions([flag], [])[0]
    try:
        owner = type("Owner", (), {"pid_file": "unused.pdf"})()
        viewer = ReviewWindow._show_question(owner, q, root)
        assert "ZZQ-7" in viewer.note_text.get("1.0", "end")
        viewer.step(1)
        assert "ABQ-123" in viewer.note_text.get("1.0", "end")
        assert "page 3" in viewer.counter.cget("text")
        viewer.destroy()
    finally:
        root.destroy()


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="Tk requires a display")
def test_circle_remains_visible_and_tracks_location_at_all_zoom_levels(monkeypatch):
    root = tk.Tk()
    root.withdraw()
    monkeypatch.setattr(LocationViewer, "_page_image",
                        lambda self, page: (Image.new("RGB", (1800, 1200), "white"), 600.0, 400.0))
    q = _questions()[0]
    try:
        viewer = LocationViewer(root, "unused.pdf", "Review", q["locations"], question=q)
        for zoom in (0.15, 1, 8):
            viewer.set_zoom(zoom)
            items = viewer.canvas.find_withtag("location_highlight")
            assert len(items) == 2
            x0, y0, x1, y1 = viewer.canvas.coords(items[-1])
            assert x1 - x0 == 60 and y1 - y0 == 60
            note = viewer.canvas.find_withtag("all")[-1]
            nx, ny = viewer.canvas.coords(note)
            assert nx + 310 <= x0 or nx >= x1
        viewer.step(1)
        assert "P-2 - Pump" in viewer.note_text.get("1.0", "end")
        viewer.destroy()

        page_viewer = LocationViewer(root, "unused.pdf", "Whole page", [], page=1)
        assert not page_viewer.canvas.find_withtag("location_highlight")
        assert "whole page" in page_viewer.counter.cget("text")
        page_viewer.destroy()
    finally:
        root.destroy()


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="Tk requires a display")
def test_page_only_flag_opens_without_circle_and_can_pan(monkeypatch):
    root = tk.Tk()
    root.withdraw()
    monkeypatch.setattr(LocationViewer, "_page_image",
                        lambda self, page: (Image.new("RGB", (1800, 1200), "white"), 600.0, 400.0))
    flag = {"type": "no_text_layer", "severity": "warning", "page": 50,
            "message": "Page 50 has no readable text."}
    q = build_questions([flag], [])[0]
    try:
        owner = type("Owner", (), {"pid_file": "unused.pdf"})()
        viewer = ReviewWindow._show_question(owner, q, root)
        assert "location unknown" in viewer.counter.cget("text")
        assert not viewer.canvas.find_withtag("location_highlight")
        assert "Page 50" in viewer.note_text.get("1.0", "end")
        viewer.set_zoom(2)
        event = type("Event", (), {"x": 400, "y": 250})()
        viewer._start_drag(event)
        event.x = 300
        viewer._pan(event)
        assert viewer.pan_x > 0
        viewer.toggle_note()
        assert not viewer.note_visible
        viewer.destroy()
    finally:
        root.destroy()


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="Tk requires a display")
def test_uncompleted_scan_issues_can_open_page(monkeypatch, tmp_path):
    from app.gui import job_manager_gui as gui

    monkeypatch.setattr(gui, "get_upload_dir", lambda: str(tmp_path / "jobs"))
    monkeypatch.setattr(gui.JobManagerApp, "_check_updates", lambda self: None)
    review = {"pid_file": "drawing.pdf", "result": {"questions": [
        {"type": "ocr_unavailable", "page": 7, "message": "OCR unavailable"},
    ]}}
    monkeypatch.setattr(gui, "load_current_clarification", lambda *_: review)
    calls = []
    monkeypatch.setattr(gui, "LocationViewer", lambda *args, **kwargs: calls.append((args, kwargs)))
    root = gui.JobManagerApp()
    root.withdraw()
    try:
        root.review_scan_issues("101")
        window = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
        next(w for w in window.winfo_children() if isinstance(w, tk.Button)).invoke()
        assert calls[0][0][3] == [{"page": 7}]
        assert calls[0][1]["question"]["flag_type"] == "ocr_unavailable"
    finally:
        root.destroy()
