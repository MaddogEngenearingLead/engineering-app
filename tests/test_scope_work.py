import json
import os
from pathlib import Path

import pdfplumber
import pytest

from app.job_manager import JobManager
from app.services.bom_export import export_bom_to_json, export_bom_to_pdf
from app.services.job_scan import run_job_scan
from app.services.scope_work import approve_scope_draft, load_scope_draft, summarize_scope


@pytest.fixture(autouse=True)
def _required_ai(required_ai):
    pass


def test_scope_summary_and_pdf_escape(tmp_path):
    scope = ("Project contact: Example Name.\nInstall valve <V-1> & gasket.\n"
             "Install valve <V-1> & gasket.\nExclude existing piping.")
    expected = ["Install valve <V-1> & gasket.", "Exclude existing piping."]
    assert summarize_scope(scope) == expected
    pdf = export_bom_to_pdf("1", "drawing.pdf", [], scope, output_dir=str(tmp_path))
    with pdfplumber.open(pdf) as document:
        text = "\n".join(page.extract_text() or "" for page in document.pages)
    assert "Install valve <V-1> & gasket." in text
    assert "Exclude existing piping." in text
    data = json.loads(Path(export_bom_to_json("1", "drawing.pdf", [], scope,
                                              output_dir=str(tmp_path))).read_text())
    assert data["scope_of_work"] == scope
    assert data["scope_summary"] == expected


def test_job_requires_scope_review_and_rescan(freetext_pdf, tmp_path):
    jm = JobManager(str(tmp_path / "jobs"))
    jm.add_job_files("101", str(freetext_pdf))
    result = run_job_scan(jm, "101")
    assert result["status"] == "needs_scope_review"
    assert result["draft"]["generation_method"] == "ai"
    assert jm.get_scope_files("101") == []
    draft = load_scope_draft(jm, "101")
    assert "Confirm intended work" in draft["text"]
    approved = "Installation:\n- Install TK-1.\n- Exclude existing piping."
    path = approve_scope_draft(jm, "101", approved)
    assert path.read_text().strip() == approved
    assert jm.get_scope_files("101")[0] == path
    with pytest.raises(ValueError):
        load_scope_draft(jm, "101")
    result = run_job_scan(jm, "101", draft["demo_pages"], draft["new_work_pages"])
    assert result["status"] == "completed"
    data = json.loads(Path(result["result"]["bom_json"]).read_text())
    assert data["scope_of_work"] == approved
    assert "Exclude existing piping." in data["scope_summary"]


def test_scan_uses_ollama_when_primary_ai_is_unconfigured(freetext_pdf, tmp_path, monkeypatch):
    from app.services import ai_review

    jm = JobManager(str(tmp_path / "jobs"))
    jm.add_job_files("101", str(freetext_pdf))

    class LocalFallback:
        name, model = "ollama", "qwen3-vl:4b"

    def missing_provider():
        raise ai_review.AIError("No API key set.")

    monkeypatch.setattr(ai_review, "get_provider", missing_provider)
    monkeypatch.setattr(ai_review, "OllamaProvider", LocalFallback)
    outcome = run_job_scan(jm, "101")
    assert outcome["status"] == "needs_scope_review"
    assert outcome["draft"]["generation_method"] == "ai"


def test_scan_ai_failure_prevents_completion(freetext_pdf, tmp_path, monkeypatch):
    from app.services import ai_review

    jm = JobManager(str(tmp_path / "jobs"))
    jm.add_job_files("101", str(freetext_pdf))
    jm.save_scope_file("101", "scope.txt", b"Install TK-1.")

    def fail(*args, **kwargs):
        raise ai_review.AIError("provider unavailable")

    monkeypatch.setattr(ai_review, "review_with_ai", fail)
    outcome = run_job_scan(jm, "101")
    assert outcome["status"] == "error"
    assert "provider unavailable" in outcome["message"]
    assert not (jm.get_job_dirs("101")[0] / "bom_exports" / "review.json").exists()


def test_failure_report_preserves_ai_codes_without_sensitive_error_text(freetext_pdf, tmp_path, monkeypatch):
    from app.services import ai_review, ollama_runtime

    jm = JobManager(str(tmp_path / "jobs"))
    jm.add_job_files("26-114", str(freetext_pdf))
    jm.save_scope_file("26-114", "scope.txt", b"secret scope wording")

    def fail(*args, **kwargs):
        try:
            raise ollama_runtime.OllamaHTTPError("/api/chat", 400, "image rejected SECRET-API-KEY")
        except ollama_runtime.OllamaHTTPError as local:
            raise ai_review.AIError(
                "provider error SECRET-API-KEY secret scope wording",
                failures=[{"provider": "gemini", "http_status": 503}]) from local

    monkeypatch.setattr(ai_review, "review_with_ai", fail)
    outcome = run_job_scan(jm, "26-114")

    assert outcome["status"] == "error"
    path = Path(outcome["diagnostic_path"])
    text = path.read_text()
    report = json.loads(text)
    assert path.parent == jm.base_dir.resolve().parent / "error"
    assert report["job_number"] == "26-114"
    assert report["stage"] == "ai_review"
    assert report["provider_failures"] == [
        {"provider": "gemini", "http_status": 503},
        {"provider": "ollama", "http_status": 400, "endpoint": "/api/chat",
         "category": "image_or_vision", "model": ollama_runtime.OLLAMA_MODEL},
    ]
    assert "SECRET-API-KEY" not in text and "secret scope wording" not in text
    assert str(tmp_path) not in text


def test_failure_report_keeps_older_reports_in_place(freetext_pdf, tmp_path, monkeypatch):
    from app.services import ai_review

    jm = JobManager(str(tmp_path / "Jobs"))
    jm.add_job_files("101", str(freetext_pdf))
    jm.save_scope_file("101", "scope.txt", b"Install TK-1.")
    old_dir = jm.base_dir / "diagnostics"
    old_dir.mkdir()
    old = old_dir / "earlier.json"
    old.write_text("{}")

    def fail(*args, **kwargs):
        raise ai_review.AIError("provider unavailable")

    monkeypatch.setattr(ai_review, "review_with_ai", fail)
    outcome = run_job_scan(jm, "101")
    assert Path(outcome["diagnostic_path"]).parent == tmp_path / "error"
    assert old.read_text() == "{}"


def test_report_write_failure_is_visible(freetext_pdf, tmp_path, monkeypatch):
    from app.services import ai_review, diagnostics

    jm = JobManager(str(tmp_path / "jobs"))
    jm.add_job_files("101", str(freetext_pdf))
    jm.save_scope_file("101", "scope.txt", b"Install TK-1.")

    def fail(*args, **kwargs):
        raise ai_review.AIError("provider unavailable")

    def no_report(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(ai_review, "review_with_ai", fail)
    monkeypatch.setattr(diagnostics, "write_failure_report", no_report)
    outcome = run_job_scan(jm, "101")
    assert "provider unavailable" in outcome["message"]
    assert "Could not save the debug report: disk full" in outcome["message"]
    assert outcome["diagnostic_path"] is None


def test_reject_stale_draft_and_existing_scope(freetext_pdf, tmp_path):
    jm = JobManager(str(tmp_path / "jobs"))
    jm.add_job_files("101", str(freetext_pdf))
    assert run_job_scan(jm, "101")["status"] == "needs_scope_review"
    pid = jm.get_pid_files("101")[0]
    original = pid.read_bytes()
    pid.write_bytes(original + b"changed")
    with pytest.raises(ValueError, match="P&ID changed"):
        approve_scope_draft(jm, "101", "Install valve.")
    assert not jm.get_scope_files("101")
    pid.write_bytes(original)
    jm.save_scope_file("101", "existing.txt", b"Original scope")
    with pytest.raises(ValueError, match="already exists"):
        approve_scope_draft(jm, "101", "Replacement")
    assert jm.get_scope_files("101")[0].read_text() == "Original scope"


def test_draft_includes_drawing_notes_even_for_embedded_bom(tmp_path):
    from app.services.scope_work import create_scope_draft
    from tests.conftest import make_pdf

    pdf = make_pdf(tmp_path / "drawing.pdf", [(["Install a new valve at tank TK-1."], (0, 0, 0))])
    jm = JobManager(str(tmp_path / "jobs"))
    jm.add_job_files("101", str(pdf))
    draft = create_scope_draft(jm, "101", jm.get_pid_files("101")[0],
                               {"new_work_pages": [], "materials": []})
    assert "Install a new valve" in draft["text"]
    assert not jm.get_scope_files("101")


def test_scope_draft_links_explicit_identifiers_but_does_not_invent_work(tmp_path):
    from app.services.scope_work import create_scope_draft
    from tests.conftest import make_pdf

    pdf = make_pdf(tmp_path / "drawing.pdf", [
        (["Replace V-101 with a new valve.", "Remove V-102 and retain V-103.",
          "Install ITEM 12 at V-101.", "Provide insulation."], (0, 0, 0)),
    ])
    jm = JobManager(str(tmp_path / "jobs"))
    jm.add_job_files("101", str(pdf))
    result = {"materials": [
        {"tag_id": "V-101", "description": "Control valve", "quantity": 2, "unit": "ea",
         "origin": "drawing", "location": "p1"},
        {"tag_id": "V-102", "description": "Valve", "origin": "drawing", "location": "p1"},
        {"tag_id": "V-104", "description": "Valve", "origin": "drawing", "location": "p1"},
        {"tag_id": "12", "description": "Pipe", "origin": "drawing_bom", "location": "p1",
         "supplied_by": "OWNER", "installed_by": "CONTRACTOR"},
    ]}
    text = create_scope_draft(jm, "101", jm.get_pid_files("101")[0], result)["text"]
    assert "Replace V-101 with a new valve" in text and "drawing quantity: 2 ea" in text
    assert "Remove V-102 and retain V-103" in text
    assert "no item-specific instruction" in text and "quantity unknown" in text
    assert "Install ITEM 12 at V-101" in text and "installed by: CONTRACTOR" in text
    assert "Provide insulation" in text


def test_ai_scope_draft_groups_tasks_and_keeps_only_valid_evidence(tmp_path, monkeypatch):
    from app.services import ai_review
    from app.services.scope_work import _format_ai_scope, create_scope_draft
    from tests.conftest import make_pdf

    pdf = make_pdf(tmp_path / "drawing.pdf", [
        (["CONTRACTOR TO INSTALL NEW VALVE V-101.", "REMOVE EXISTING LINE."], (0, 0, 0)),
    ])
    jm = JobManager(str(tmp_path / "jobs"))
    jm.add_job_files("101", str(pdf))
    result = {"new_work_pages": [1], "materials": [
        {"tag_id": "11", "description": "12 inch flange", "quantity": None,
         "origin": "drawing_bom", "unit": "", "page": 4},
    ]}
    monkeypatch.setattr(ai_review, "is_configured", lambda: True)
    def fake_draft(drawing, bom, review_index=""):
        assert "P1:" in drawing
        assert "BOM-11 | 11 | 12 inch flange | drawing page 4" in bom
        assert "Confirm intended work" in review_index
        return {
        "provider": "gemini", "model": "test-model", "sections": [
            {"title": "Phase 1: Mechanical work", "tasks": [
                {"text": "Install V-101.", "sources": ["P1"], "verify": False},
                {"text": "Install all 12 inch flanges.", "sources": ["BOM-11"], "verify": True},
                {"text": "Invented task.", "sources": ["P999"], "verify": False},
            ]},
        ],
        }
    monkeypatch.setattr(ai_review, "draft_scope_with_ai", fake_draft)
    draft = create_scope_draft(jm, "101", jm.get_pid_files("101")[0], result)
    assert draft["generation_method"] == "ai"
    assert draft["ai_provider"] == "gemini"
    assert "Phase 1: Mechanical work" in draft["text"]
    assert "drawing page 1" in draft["text"]
    assert "BOM item 11, drawing page 4" in draft["text"]
    assert "P999" not in draft["text"] and "Invented task" not in draft["text"]
    assert "[VERIFY]" in draft["text"]


def test_ai_scope_draft_failure_blocks_scope_draft(tmp_path, monkeypatch):
    from app.services import ai_review
    from app.services.scope_work import create_scope_draft
    from tests.conftest import make_pdf

    pdf = make_pdf(tmp_path / "drawing.pdf", [(["Install valve V-101."], (0, 0, 0))])
    jm = JobManager(str(tmp_path / "jobs"))
    jm.add_job_files("101", str(pdf))
    monkeypatch.setattr(ai_review, "is_configured", lambda: True)

    def fail(*args, **kwargs):
        raise ai_review.AIError("provider unavailable")

    monkeypatch.setattr(ai_review, "draft_scope_with_ai", fail)
    with pytest.raises(ai_review.AIError, match="provider unavailable"):
        create_scope_draft(jm, "101", jm.get_pid_files("101")[0], {"materials": []})


def test_scope_ai_formatter_rejects_all_untraceable_tasks():
    from app.services.scope_work import _format_ai_scope

    with pytest.raises(ValueError, match="traceable"):
        _format_ai_scope({"sections": [
            {"title": "Phase 1", "tasks": [
                {"text": "Unsupported task.", "sources": ["BOM-999"], "verify": True}
            ]}
        ]}, {"P1"})


def test_ai_bom_evidence_preserves_unstated_quantity_and_marks_transcription():
    from app.services.scope_work import _bom_evidence

    text, sources, labels = _bom_evidence([
        {"tag_id": "12", "description": "Flange", "origin": "drawing_bom", "page": 4, "quantity": None},
        {"tag_id": "13", "description": "Valve", "origin": "drawing_bom_ai", "page": 5, "quantity": 2},
    ])
    assert "BOM-12 | 12 | Flange | drawing page 4" in text
    assert "AI-BOM-13 | 13 | Valve; quantity: 2 | drawing page 5" in text
    assert "quantity: None" not in text
    assert sources == {"BOM-12", "AI-BOM-13"}
    assert labels["AI-BOM-13"] == "AI-transcribed BOM item 13, drawing page 5"


def test_job_scope_api_review(freetext_pdf, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import routes
    from app.main import app
    from app.config import settings

    jm = JobManager(str(tmp_path / "jobs"))
    jm.add_job_files("101", str(freetext_pdf))
    monkeypatch.setattr(routes, "job_manager", jm)
    client = TestClient(app)
    base = f"{settings.api_prefix}/jobs/101"
    response = client.post(base + "/scan")
    assert response.status_code == 200
    assert response.json()["status"] == "needs_scope_review"
    assert client.get(base + "/scope-draft").status_code == 200
    assert not jm.get_scope_files("101")
    response = client.post(base + "/scope-draft/approve", data={"scope_of_work": "Install TK-1."})
    assert response.status_code == 200
    assert jm.get_scope_files("101")[0].read_text().strip() == "Install TK-1."
    assert client.post(base + "/scan").json()["status"] == "completed"


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="Tk requires a display")
def test_desktop_scope_review_cancel_and_approve(freetext_pdf, tmp_path, monkeypatch):
    import tkinter as tk
    from app.gui import job_manager_gui as gui

    monkeypatch.setattr(gui, "get_upload_dir", lambda: str(tmp_path / "jobs"))
    monkeypatch.setattr(gui.JobManagerApp, "_check_updates", lambda self: None)
    app = gui.JobManagerApp()
    app.withdraw()
    try:
        app.jobs.add_job_files("101", str(freetext_pdf))
        assert run_job_scan(app.jobs, "101")["status"] == "needs_scope_review"
        scans = []
        monkeypatch.setattr(app, "start_scan", lambda *args: scans.append(args))
        app.review_scope("101")
        dialog = next(w for w in app.winfo_children() if isinstance(w, tk.Toplevel))
        buttons = next(w for w in dialog.winfo_children() if isinstance(w, tk.Frame))
        next(w for w in buttons.winfo_children() if w.cget("text") == "Cancel").invoke()
        assert not app.jobs.get_scope_files("101") and not scans
        app.review_scope("101")
        dialog = next(w for w in app.winfo_children() if isinstance(w, tk.Toplevel))
        editor = next(w for w in dialog.winfo_children() if isinstance(w, tk.Text))
        editor.delete("1.0", "end")
        editor.insert("1.0", "Install TK-1.")
        buttons = next(w for w in dialog.winfo_children() if isinstance(w, tk.Frame))
        next(w for w in buttons.winfo_children() if w.cget("text") == "Approve and generate scope").invoke()
        assert app.jobs.get_scope_files("101")[0].read_text().strip() == "Install TK-1."
        assert scans == [("101", [2], [3])]
    finally:
        app.destroy()
