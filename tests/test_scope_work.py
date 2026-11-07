import json
import os
from pathlib import Path

import pdfplumber
import pytest

from app.job_manager import JobManager
from app.services.bom_export import export_bom_to_json, export_bom_to_pdf
from app.services.job_scan import run_job_scan
from app.services.scope_work import approve_scope_draft, load_scope_draft, summarize_scope


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
    assert "Drawing page 1, possible work note: Install a new valve" in draft["text"]
    assert not jm.get_scope_files("101")


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
