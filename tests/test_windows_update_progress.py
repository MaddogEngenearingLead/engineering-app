from pathlib import Path
import zipfile

from app.services import updater


def test_windows_update_helper_shows_aggregate_install_percent(tmp_path, monkeypatch):
    install = tmp_path / "installed"
    install.mkdir()
    executable = install / "JobManager.exe"
    executable.write_text("old")
    (install / "_internal").mkdir()
    download = tmp_path / "update" / "JobManager-windows.zip"
    download.parent.mkdir()
    with zipfile.ZipFile(download, "w") as archive:
        archive.writestr("JobManager.exe", "new")
        archive.writestr("_internal/runtime.dll", b"runtime-data")

    monkeypatch.setattr(updater.sys, "platform", "win32")
    monkeypatch.setattr(updater.sys, "executable", str(executable))
    monkeypatch.setattr(updater.subprocess, "Popen", lambda *args, **kwargs: None)

    updater.apply_update(download)

    batch = (download.parent / "apply_update.bat").read_text()
    helper = (download.parent / "copy_runtime.ps1").read_text()
    assert "Waiting for Engineering App to close" in batch
    assert "powershell.exe" in batch
    assert "Installing executable: 100%" in batch
    assert "Installing runtime: {0}%" in helper
    assert "[Math]::Floor(100 * $copied / $total)" in helper
