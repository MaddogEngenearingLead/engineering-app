import httpx

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
    _patch(monkeypatch, 200, _release("v2.0.0", ["JobManager.exe", "JobManager-macos.zip"]))
    info = updater.check_for_update("1.0.0")
    assert info and info.version == "2.0.0" and info.asset_name == "JobManager.exe"


def test_macos_asset(monkeypatch):
    _patch(monkeypatch, 200, _release("v2.0.0", ["JobManager.exe", "JobManager-macos.zip"]), "darwin")
    assert updater.check_for_update("1.0.0").asset_name == "JobManager-macos.zip"


def test_no_update_when_current(monkeypatch):
    _patch(monkeypatch, 200, _release("v1.0.0", ["JobManager.exe"]))
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
    info = updater.UpdateInfo("2.0.0", "", "JobManager.exe", "https://x/a")
    assert updater.download_update(info, tmp_path).read_bytes() == b"binary"


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
