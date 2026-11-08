from pathlib import Path
from types import SimpleNamespace

from app.gui import job_manager_gui


def test_scan_failure_offers_to_save_report(monkeypatch, tmp_path):
    seen = []
    report = tmp_path / "failure.json"
    report.write_text("{}")
    app = SimpleNamespace(running={"26-114"}, show_dashboard=lambda: None,
                          save_debug_report=lambda path: seen.append(path))
    monkeypatch.setattr(job_manager_gui.messagebox, "askyesno", lambda *args, **kwargs: True)

    job_manager_gui.JobManagerApp._scan_done(
        app, "26-114", {"status": "error", "message": "failed", "diagnostic_path": str(report)})

    assert app.running == set()
    assert seen == [report]


def test_save_debug_report_copies_only_report(monkeypatch, tmp_path):
    report = tmp_path / "report.json"
    report.write_text('{"stage":"ai_review"}')
    destination = tmp_path / "share.json"
    monkeypatch.setattr(job_manager_gui.filedialog, "asksaveasfilename", lambda **kwargs: str(destination))

    job_manager_gui.JobManagerApp.save_debug_report(object(), report)

    assert destination.read_text() == report.read_text()


def test_open_debug_reports_uses_jobs_directory(monkeypatch, tmp_path):
    opened = []
    app = SimpleNamespace(jobs=SimpleNamespace(base_dir=tmp_path))
    monkeypatch.setattr(job_manager_gui, "open_path", opened.append)

    job_manager_gui.JobManagerApp.open_debug_reports(app)

    assert opened == [str((tmp_path / "diagnostics").resolve())]
    assert Path(opened[0]).is_dir()


def test_update_failure_message_survives_deferred_callback(monkeypatch):
    callbacks = []
    failures = []

    class Thread:
        def __init__(self, target, daemon):
            self.target = target

        def start(self):
            self.target()

    def fail(*args, **kwargs):
        raise RuntimeError("network disconnected")

    app = SimpleNamespace(updating=False, update_info=object(), running=set(),
                          _render_update_banner=lambda: None,
                          _update_failed=failures.append,
                          after=lambda delay, callback: callbacks.append(callback),
                          destroy=lambda: None)
    monkeypatch.setattr(job_manager_gui.threading, "Thread", Thread)
    monkeypatch.setattr(job_manager_gui, "download_update", fail)

    job_manager_gui.JobManagerApp.start_update(app)
    for callback in callbacks:
        callback()
    assert failures == ["network disconnected"]
