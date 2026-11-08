import json
import os
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.gui.job_manager_gui import JobManagerApp
from app.job_manager import JobManager


def test_delete_job_removes_only_job_owned_files(tmp_path):
    jm = JobManager(str(tmp_path / "jobs"))
    original = tmp_path / "original.pdf"
    original.write_bytes(b"original")
    jm.add_job_files("26-144(2)", str(original))
    job_dir, _, _ = jm.get_job_dirs("26-144(2)")
    (job_dir / "bom_exports" / "review.json").write_text("review")
    external = tmp_path / "external.txt"
    external.write_text("external")
    (job_dir / "outside-link").symlink_to(external)
    jm.add_job_files("other", str(original))

    jm.delete_job("26-144(2)")

    assert not job_dir.exists()
    assert not jm.job_file_path("26-144(2)").exists()
    assert original.read_bytes() == b"original"
    assert external.read_text() == "external"
    assert [job["job_number"] for job in jm.list_jobs()] == ["other"]


def test_delete_job_rejects_colliding_job_number(tmp_path):
    jm = JobManager(str(tmp_path))
    jm.create_job("A/B")
    with pytest.raises(ValueError, match="does not match"):
        jm.delete_job("A-B")
    assert jm.get_job_dirs("A/B")[0].exists()


def test_delete_job_rejects_symlinked_directory_or_record(tmp_path):
    jm = JobManager(str(tmp_path / "jobs"))
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "job_metadata.json").write_text(json.dumps({"job_number": "unsafe"}))
    (jm.base_dir / "unsafe").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic link"):
        jm.delete_job("unsafe")
    assert (outside / "job_metadata.json").exists()
    jm.create_job("another")
    jm.job_file_path("another").symlink_to(outside / "job_metadata.json")
    with pytest.raises(ValueError, match="symbolic link"):
        jm.delete_job("another")
    assert jm.get_job_dirs("another")[0].exists()


def test_delete_job_surfaces_removal_failure(tmp_path, monkeypatch):
    jm = JobManager(str(tmp_path))
    jm.save_pid_file("101", "drawing.pdf", b"pdf")
    def fail(_path):
        raise PermissionError("locked")
    monkeypatch.setattr("app.job_manager.shutil.rmtree", fail)
    with pytest.raises(PermissionError, match="locked"):
        jm.delete_job("101")
    assert jm.job_file_path("101").exists()


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="Tk requires a display")
def test_dashboard_delete_confirmation_and_running_guard(tmp_path, monkeypatch):
    from app.gui import job_manager_gui

    root = tk.Tk()
    root.withdraw()
    jm = JobManager(str(tmp_path))
    jm.create_job("101")
    refreshed = []
    app = SimpleNamespace(jobs=jm, running=set(), winfo_children=root.winfo_children,
                          show_dashboard=lambda: refreshed.append(True))
    answers = []
    monkeypatch.setattr(job_manager_gui.messagebox, "askyesno", lambda *a, **k: answers.pop(0))
    warnings = []
    monkeypatch.setattr(job_manager_gui.messagebox, "showwarning", lambda *a, **k: warnings.append(a))
    try:
        answers.append(False)
        JobManagerApp.delete_job(app, "101")
        assert jm.get_job_dirs("101")[0].exists()
        app.running.add("101")
        JobManagerApp.delete_job(app, "101")
        assert warnings and jm.get_job_dirs("101")[0].exists()
        app.running.clear()
        dialog = tk.Toplevel(root)
        dialog.job_number_for_delete = "101"
        answers.append(True)
        JobManagerApp.delete_job(app, "101")
        assert not dialog.winfo_exists()
        assert jm.get_job_dirs("101")[0] is None
        assert refreshed == [True]
    finally:
        root.destroy()
