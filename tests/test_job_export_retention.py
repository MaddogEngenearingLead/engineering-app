import json
import builtins
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.api import routes
from app.config import settings
from app.job_manager import JobManager
from app.main import app
from app.services import bom_export, scope_bom
from app.services.job_scan import load_current_clarification, load_completed_review, load_review, run_job_scan, save_review


KEYS = ("bom_pdf", "bom_json", "bom_csv")


def test_long_scope_does_not_hide_materials_and_full_scope_is_preserved(tmp_path):
    materials = [{"item_number": 1, "tag_id": "11", "description": "Flange", "type": "flange",
                  "quantity": 2, "unit": "ea", "location": "BOM page 4", "confidence": 0.95}]
    scope = "\n".join(f"Install item {n} according to the drawing." for n in range(1, 101))
    result = bom_export.export_all("JOB-101", "drawing.pdf", materials, scope, [], [], str(tmp_path))
    pages = [page.extract_text() for page in PdfReader(result["bom_pdf"]).pages]
    assert "Equipment & Materials" in pages[0] and "Flange" in pages[0]
    pdf_text = "\n".join(pages)
    assert "Showing 12 of 100 extracted statements" in pdf_text
    assert "Install item 12" in pdf_text and "Install item 13" not in pdf_text
    data = json.loads(Path(result["bom_json"]).read_text(encoding="utf-8"))
    assert data["scope_of_work"] == scope
    assert len(data["scope_summary"]) == 100


def test_unicode_csv_is_utf8_when_system_default_is_windows_encoding(tmp_path, monkeypatch):
    original_open = builtins.open

    def windows_default(file, mode="r", *args, **kwargs):
        if str(file).endswith(".csv") and "w" in mode and "encoding" not in kwargs:
            kwargs["encoding"] = "cp1252"
        return original_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", windows_default)
    with bom_export.staged_job_exports(str(tmp_path)) as stage:
        files = bom_export.export_all(
            "JOB-101", "drawing.pdf",
            [{"item_number": 1, "tag_id": "V-1", "description": "90° elbow",
              "type": "fitting", "quantity": 1, "unit": "ea", "confidence": 1.0}],
            "Install the elbow.", [], [], str(stage))
        published = bom_export.publish_job_exports("JOB-101", stage, files, str(tmp_path))
    assert "90° elbow" in Path(published["bom_csv"]).read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _required_ai(required_ai):
    pass


@pytest.fixture
def job(tmp_path, freetext_pdf):
    jm = JobManager(str(tmp_path / "jobs"))
    jm.add_job_files("101", freetext_pdf)
    jm.save_scope_file("101", "scope.txt", b"Install TK-1.")
    return jm


def snapshot(result):
    return {key: (Path(result[key]), Path(result[key]).read_bytes()) for key in KEYS}


def assert_preserved(files):
    for path, content in files.values():
        assert path.read_bytes() == content


def test_gui_regeneration_and_review_remove_only_job_exports(job):
    first = run_job_scan(job, "101")
    assert first["status"] == "completed"
    previous = snapshot(first["result"])
    directory = next(iter(previous.values()))[0].parent
    legacy = [directory / f"BOM_JOB-101_20200101_010203.{ext}" for ext in ("pdf", "json", "csv")]
    unrelated = [directory / name for name in (
        "BOM_JOB-1010_20200101_010203.pdf", "BOM_JOB-101_20200101_010203_notes.pdf",
        "BOM_JOB-101_notes.json", "review.json.backup", "my-bom.csv")]
    for path in legacy + unrelated:
        path.write_text("untouched")
    review = load_review(job, "101")
    paths = save_review(job, "101", review["materials"], ["confirmed"])
    assert all(not path.exists() for path, _ in previous.values())
    assert all(not path.exists() for path in legacy)
    assert all(path.read_text() == "untouched" for path in unrelated)
    assert json.loads(Path(paths["bom_json"]).read_text())["clarifications"] == ["confirmed"]
    second = run_job_scan(job, "101")
    assert second["status"] == "completed"
    assert all(not Path(path).exists() for path in paths.values())
    assert all(Path(second["result"][key]).is_file() for key in KEYS)
    assert all(path.exists() for path in unrelated)


@pytest.mark.parametrize("kind", ["exception", "missing", "corrupt", "clarification", "scope_review"])
def test_gui_failure_keeps_previous_outputs_and_review(job, monkeypatch, kind):
    first = run_job_scan(job, "101")
    previous = snapshot(first["result"])
    old_review = load_review(job, "101")
    if kind == "scope_review":
        monkeypatch.setattr(job, "get_scope_files", lambda number: [])
    elif kind == "clarification":
        monkeypatch.setattr(scope_bom, "build_scoped_bom",
                            lambda *a, **k: {"status": "needs_clarification", "questions": [{"message": "?"}]})
    elif kind == "exception":
        monkeypatch.setattr(scope_bom, "build_scoped_bom", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fail")))
    else:
        original = scope_bom.build_scoped_bom
        def faulty(*args, **kwargs):
            result = original(*args, **kwargs)
            if kind == "missing":
                result["bom_csv"] = None
            else:
                Path(result["bom_json"]).write_text("not json")
            return result
        monkeypatch.setattr(scope_bom, "build_scoped_bom", faulty)
    result = run_job_scan(job, "101")
    assert result["status"] == {"clarification": "needs_clarification", "scope_review": "needs_scope_review"}.get(kind, "error")
    assert_preserved(previous)
    assert load_completed_review(job, "101") == old_review
    if kind == "clarification":
        assert load_review(job, "101") == load_current_clarification(job, "101")
        assert load_review(job, "101")["result"]["questions"][0]["message"] == "?"
    else:
        assert load_review(job, "101") == old_review


def test_review_failure_keeps_previous(job, monkeypatch):
    previous = snapshot(run_job_scan(job, "101")["result"])
    review = load_review(job, "101")
    def fail(*args, **kwargs):
        raise RuntimeError("export failed")
    monkeypatch.setattr(bom_export, "export_bom_to_csv", fail)
    with pytest.raises(RuntimeError, match="export failed"):
        save_review(job, "101", review["materials"], ["change"])
    assert_preserved(previous)
    assert load_review(job, "101") == review


def test_job_api_retention(job, monkeypatch):
    monkeypatch.setattr(routes, "job_manager", job)
    client = TestClient(app)
    url = f"{settings.api_prefix}/jobs/101/scan"
    first = client.post(url)
    assert first.status_code == 200 and first.json()["status"] == "completed"
    previous = snapshot(first.json())
    original = routes.build_scoped_bom
    def incomplete(*args, **kwargs):
        result = original(*args, **kwargs)
        result["bom_pdf"] = None
        return result
    monkeypatch.setattr(routes, "build_scoped_bom", incomplete)
    assert client.post(url).status_code == 500
    assert_preserved(previous)
    monkeypatch.setattr(routes, "build_scoped_bom",
                        lambda *a, **k: {"status": "needs_clarification", "questions": [{"message": "?"}]})
    assert client.post(url).json()["status"] == "needs_clarification"
    assert_preserved(previous)
    monkeypatch.setattr(routes, "build_scoped_bom", original)
    scope_file = job.get_scope_files("101")[0]
    scope_file.unlink()
    scope_review = client.post(url)
    assert scope_review.json()["status"] == "needs_scope_review"
    assert not any(key in scope_review.json() for key in KEYS)
    assert_preserved(previous)
    scope_file.write_text("Install TK-1.")
    second = client.post(url).json()
    assert second["status"] == "completed"
    assert all(not path.exists() for path, _ in previous.values())
    assert all(Path(second[key]).is_file() for key in KEYS)


def test_job_api_reports_cleanup_failure(job, monkeypatch):
    monkeypatch.setattr(routes, "job_manager", job)
    client = TestClient(app)
    url = f"{settings.api_prefix}/jobs/101/scan"
    first = client.post(url).json()
    target = Path(first["bom_pdf"])
    original = Path.unlink
    def refuse(self, *args, **kwargs):
        if self == target:
            raise PermissionError("locked")
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", refuse)
    result = client.post(url).json()
    assert result["status"] == "completed" and "could not be removed" in result["cleanup_warning"]
    assert target.exists() and all(Path(result[key]).is_file() for key in KEYS)


def test_one_off_scan_does_not_prune_prior_scans(freetext_pdf, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    client = TestClient(app)
    def scan():
        with open(freetext_pdf, "rb") as f:
            response = client.post(f"{settings.api_prefix}/scan",
                                   files={"file": ("drawing.pdf", f, "application/pdf")},
                                   data={"scope_of_work": "Install TK-1."})
        assert response.status_code == 200 and response.json()["status"] == "completed"
        return response.json()
    previous = snapshot(scan())
    scan()
    assert_preserved(previous)


def test_review_metadata_failure_rolls_back(job, monkeypatch):
    from app.services import job_scan
    previous = snapshot(run_job_scan(job, "101")["result"])
    review = load_review(job, "101")
    original = job_scan._store
    def fail_after_store(*args):
        original(*args)
        raise OSError("metadata failed")
    monkeypatch.setattr(job_scan, "_store", fail_after_store)
    with pytest.raises(OSError, match="metadata failed"):
        save_review(job, "101", review["materials"], ["changed"])
    assert_preserved(previous)
    assert load_review(job, "101") == review
    metadata = job._load_json(job.job_file_path("101"))
    assert all(metadata[key] == str(previous[key][0]) for key in KEYS)


def test_gui_metadata_failure_rolls_back(job, monkeypatch):
    from app.services import job_scan
    previous = snapshot(run_job_scan(job, "101")["result"])
    review = load_review(job, "101")
    original = job_scan._store
    def fail_on_completion(jm, number, values):
        original(jm, number, values)
        if values.get("bom_status") == "completed":
            raise OSError("metadata failed")
    monkeypatch.setattr(job_scan, "_store", fail_on_completion)
    assert run_job_scan(job, "101")["status"] == "error"
    assert_preserved(previous)
    assert load_review(job, "101") == review
    metadata = job._load_json(job.job_file_path("101"))
    assert all(metadata[key] == str(previous[key][0]) for key in KEYS)


def test_publication_move_failure_rolls_back(job, monkeypatch):
    previous = snapshot(run_job_scan(job, "101")["result"])
    original = Path.replace
    count = 0
    def fail_second(self, target):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("move failed")
        return original(self, target)
    monkeypatch.setattr(Path, "replace", fail_second)
    assert run_job_scan(job, "101")["status"] == "error"
    assert_preserved(previous)
    directory = next(iter(previous.values()))[0].parent
    assert len(list(directory.glob("BOM_JOB-101_*"))) == 3


def test_clarification_is_current_and_cleared_on_success(job, monkeypatch):
    first = run_job_scan(job, "101")
    previous = snapshot(first["result"])
    review = load_completed_review(job, "101")
    review["answers"] = {"saved": {"input": "yes"}}
    review_path = next(iter(previous.values()))[0].parent / "review.json"
    review_path.write_text(json.dumps(review))
    original = scope_bom.build_scoped_bom
    result = {"status": "needs_clarification", "questions": [
        {"message": "Current drawing issue", "type": "ocr", "locations": [{"page": 2}]}]}
    monkeypatch.setattr(scope_bom, "build_scoped_bom", lambda *a, **k: result)
    assert run_job_scan(job, "101")["status"] == "needs_clarification"
    assert load_current_clarification(job, "101")["result"] == result
    assert load_review(job, "101")["result"] == result
    assert load_completed_review(job, "101") == review
    assert_preserved(previous)
    monkeypatch.setattr(scope_bom, "build_scoped_bom",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("scan failed")))
    assert run_job_scan(job, "101")["status"] == "error"
    assert load_current_clarification(job, "101")["result"] == result
    assert_preserved(previous)
    monkeypatch.setattr(scope_bom, "build_scoped_bom", original)
    assert run_job_scan(job, "101")["status"] == "completed"
    assert load_current_clarification(job, "101") is None
    assert load_review(job, "101") == load_completed_review(job, "101")


def test_first_clarification_is_available_without_completed_review(job, monkeypatch):
    monkeypatch.setattr(scope_bom, "build_scoped_bom",
                        lambda *a, **k: {"status": "needs_clarification", "questions": [{"message": "First"}]})
    assert run_job_scan(job, "101")["status"] == "needs_clarification"
    assert load_completed_review(job, "101") is None
    assert load_review(job, "101") == load_current_clarification(job, "101")


def test_repeated_clarifications_keep_latest_and_successful_generation(job, monkeypatch):
    original_scan = scope_bom.build_scoped_bom
    previous = snapshot(run_job_scan(job, "101")["result"])
    review = load_completed_review(job, "101")
    for message in ("first issue", "second issue", "third issue"):
        monkeypatch.setattr(scope_bom, "build_scoped_bom",
                            lambda *a, message=message, **k: {
                                "status": "needs_clarification", "questions": [{"message": message}]})
        assert run_job_scan(job, "101")["status"] == "needs_clarification"
        assert load_current_clarification(job, "101")["result"]["questions"][0]["message"] == message
        assert load_completed_review(job, "101") == review
        assert_preserved(previous)
    monkeypatch.setattr(scope_bom, "build_scoped_bom", original_scan)
    second = run_job_scan(job, "101")
    assert second["status"] == "completed"
    assert load_current_clarification(job, "101") is None
    assert all(not path.exists() for path, _ in previous.values())
    previous = snapshot(second["result"])
    review = load_completed_review(job, "101")
    monkeypatch.setattr(scope_bom, "build_scoped_bom",
                        lambda *a, **k: {"status": "needs_clarification", "questions": [{"message": "new issue"}]})
    assert run_job_scan(job, "101")["status"] == "needs_clarification"
    assert load_current_clarification(job, "101")["result"]["questions"][0]["message"] == "new issue"
    assert load_completed_review(job, "101") == review
    assert_preserved(previous)


def test_clarification_clearing_failure_preserves_previous_generation(job, monkeypatch):
    previous = snapshot(run_job_scan(job, "101")["result"])
    old_review = load_completed_review(job, "101")
    original_scan = scope_bom.build_scoped_bom
    monkeypatch.setattr(scope_bom, "build_scoped_bom",
                        lambda *a, **k: {"status": "needs_clarification", "questions": [{"message": "Current"}]})
    assert run_job_scan(job, "101")["status"] == "needs_clarification"
    clarification = load_current_clarification(job, "101")
    monkeypatch.setattr(scope_bom, "build_scoped_bom", original_scan)
    original_unlink = Path.unlink
    def fail_clear(self, *args, **kwargs):
        if self.name == "clarification.json":
            raise PermissionError("locked")
        return original_unlink(self, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", fail_clear)
    assert run_job_scan(job, "101")["status"] == "error"
    assert load_current_clarification(job, "101") == clarification
    assert load_completed_review(job, "101") == old_review
    assert_preserved(previous)


@pytest.mark.parametrize("operation", ["scan", "review"])
def test_cleanup_failure_is_reported_with_published_outputs(job, monkeypatch, operation):
    first = run_job_scan(job, "101")
    previous = snapshot(first["result"])
    target = previous["bom_pdf"][0]
    original = Path.unlink
    def refuse(self, *args, **kwargs):
        if self == target:
            raise PermissionError("locked")
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", refuse)
    if operation == "scan":
        outcome = run_job_scan(job, "101")
        assert outcome["status"] == "error"
        assert "New BOM was published" in outcome["message"]
        paths = outcome["result"]
    else:
        review = load_completed_review(job, "101")
        with pytest.raises(RuntimeError, match="New BOM was published"):
            save_review(job, "101", review["materials"], [])
        paths = job._load_json(job.job_file_path("101"))
    assert target.exists()
    assert all(Path(paths[key]).is_file() for key in KEYS)
    assert "could not be removed" in job._load_json(job.job_file_path("101"))["bom_message"]
