import zipfile
import stat

import httpx
import pytest

from app.services import updater


def test_version_compare():
    assert updater.is_newer("v1.2.0", "1.1.9")
    assert updater.is_newer("v0.1.0", "0.0.0")
    assert not updater.is_newer("v1.0.0", "1.0.0")
    assert not updater.is_newer("v0.9", "1.0.0")


def _release(tag, assets):
    return {"tag_name": tag, "body": "notes", "assets": [{"name": n, "url": f"https://x/{n}"} for n in assets]}


def _patch(monkeypatch, status, payload, platform="win32"):
    monkeypatch.setattr(updater.sys, "platform", platform)
    monkeypatch.setattr(updater.httpx, "get", lambda *a, **k: httpx.Response(status, json=payload))


def test_update_found(monkeypatch):
    _patch(monkeypatch, 200, _release("v2.0.0", ["JobManager-windows.zip", "JobManager-macos.zip"]))
    info = updater.check_for_update("1.0.0")
    assert info and info.version == "2.0.0" and info.asset_name == "JobManager-windows.zip"


def test_macos_asset(monkeypatch):
    _patch(monkeypatch, 200, _release("v2.0.0", ["JobManager-windows.zip", "JobManager-macos.zip"]), "darwin")
    assert updater.check_for_update("1.0.0").asset_name == "JobManager-macos.zip"


def test_update_token_is_sent_as_bearer(monkeypatch):
    monkeypatch.setenv("UPDATE_TOKEN", "test-token")
    assert updater._headers("application/json")["Authorization"] == "Bearer test-token"


def test_no_update_when_current(monkeypatch):
    _patch(monkeypatch, 200, _release("v1.0.0", ["JobManager-windows.zip"]))
    assert updater.check_for_update("1.0.0") is None


def test_errors_are_silent(monkeypatch):
    _patch(monkeypatch, 404, {})
    assert updater.check_for_update("1.0.0") is None

    def boom(*a, **k):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(updater.httpx, "get", boom)
    assert updater.check_for_update("1.0.0") is None


def test_download(monkeypatch, tmp_path):
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=b"binary"))
    client = httpx.Client(transport=transport)
    monkeypatch.setattr(
        updater.httpx, "stream", lambda method, url, **kw: client.stream(method, url, headers=kw.get("headers"))
    )
    info = updater.UpdateInfo("2.0.0", "", "JobManager-windows.zip", "https://x/a")
    assert updater.download_update(info, tmp_path).read_bytes() == b"binary"


def test_download_reports_byte_progress(monkeypatch, tmp_path):
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=b"binary"))
    client = httpx.Client(transport=transport)
    monkeypatch.setattr(
        updater.httpx, "stream", lambda method, url, **kw: client.stream(method, url, headers=kw.get("headers"))
    )
    info = updater.UpdateInfo("2.0.0", "", "JobManager-windows.zip", "https://x/a")
    seen = []
    updater.download_update(info, tmp_path, lambda *args: seen.append(args))
    assert seen[0] == ("Downloading", 0, 6)
    assert seen[-1] == ("Downloading", 6, 6)


def test_windows_update_extracts_and_overlays_app_folder(tmp_path, monkeypatch):
    install = tmp_path / "installed"
    install.mkdir()
    executable = install / "JobManager.exe"
    executable.write_text("old")
    downloaded = tmp_path / "update" / "JobManager-windows.zip"
    downloaded.parent.mkdir()
    with zipfile.ZipFile(downloaded, "w") as archive:
        archive.writestr("JobManager.exe", "new")
        archive.writestr("_internal/app.dll", "runtime")
    monkeypatch.setattr(updater.sys, "platform", "win32")
    monkeypatch.setattr(updater.sys, "executable", str(executable))
    monkeypatch.setattr(updater.subprocess, "Popen", lambda *args, **kwargs: None)

    updater.apply_update(downloaded)

    assert (downloaded.parent / "extracted" / "JobManager.exe").read_text() == "new"
    script = (downloaded.parent / "apply_update.bat").read_text()
    assert "robocopy" in script and str(install) in script
    assert "pause" in script and "Update failed" in script


def test_windows_update_reports_unwritable_app_folder(tmp_path, monkeypatch):
    executable = tmp_path / "JobManager.exe"
    monkeypatch.setattr(updater.sys, "platform", "win32")
    monkeypatch.setattr(updater.sys, "executable", str(executable))

    def deny(*args, **kwargs):
        raise PermissionError("access denied")

    monkeypatch.setattr(updater.tempfile, "TemporaryFile", deny)
    with pytest.raises(RuntimeError, match="app folder is not writable"):
        updater.apply_update(tmp_path / "update.zip")


def test_extract_reports_progress(tmp_path):
    archive_path = tmp_path / "update.zip"
    contents = b"x" * (2 * 1024 * 1024 + 10)
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("app.bin", contents)
    seen = []
    updater._extract_update(archive_path, tmp_path / "extracted", lambda *args: seen.append(args))
    assert seen[0] == ("Extracting", 0, len(contents))
    assert seen[-1] == ("Extracting", len(contents), len(contents))
    assert len(seen) >= 4
    assert (tmp_path / "extracted" / "app.bin").read_bytes() == contents


def test_update_preserves_executable_and_symlink(tmp_path):
    downloaded = tmp_path / "update.zip"
    executable = zipfile.ZipInfo("JobManager.app/Contents/MacOS/JobManager")
    executable.external_attr = (stat.S_IFREG | 0o755) << 16
    link = zipfile.ZipInfo("JobManager.app/Contents/MacOS/tool")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(downloaded, "w") as archive:
        archive.writestr(executable, "runtime")
        archive.writestr(link, "JobManager")

    updater._extract_update(downloaded, tmp_path / "extracted")

    root = tmp_path / "extracted" / "JobManager.app" / "Contents" / "MacOS"
    assert (root / "JobManager").stat().st_mode & 0o111
    assert (root / "tool").is_symlink()
    assert (root / "tool").read_text() == "runtime"


def test_update_rejects_escaping_symlink(tmp_path):
    downloaded = tmp_path / "update.zip"
    link = zipfile.ZipInfo("unsafe")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(downloaded, "w") as archive:
        archive.writestr(link, "../outside")
    with pytest.raises(RuntimeError, match="unsafe symlink"):
        updater._extract_update(downloaded, tmp_path / "extracted")


def test_portable_jobs_folder_next_to_exe(tmp_path, monkeypatch):
    import sys
    from app.gui import job_manager_gui as g

    exe = tmp_path / "JobManager.exe"
    exe.write_text("x")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.delenv("UPLOAD_DIR", raising=False)
    monkeypatch.setattr(g.sys, "platform", "win32")
    monkeypatch.setattr(g, "_on_removable_drive", lambda p: False)
    assert "EngineeringApp" in g.get_upload_dir() or g.portable_upload_dir() is None
    (tmp_path / "Jobs").mkdir()
    assert g.get_upload_dir() == str(tmp_path / "Jobs")
    (tmp_path / "Jobs").rmdir()
    monkeypatch.setattr(g, "_on_removable_drive", lambda p: True)
    assert g.get_upload_dir() == str(tmp_path / "Jobs") and (tmp_path / "Jobs").is_dir()
