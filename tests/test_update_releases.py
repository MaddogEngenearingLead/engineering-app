import httpx

from app.services import update_releases, updater


def _release(tag, assets):
    return {"tag_name": tag, "body": f"Notes for {tag}",
            "assets": [{"name": name, "url": f"https://api.github.test/assets/{name}"}
                       for name in assets]}


def test_release_selector_includes_newer_and_older_versions(monkeypatch):
    payload = [
        _release("v0.1.40", ["JobManager-windows.zip"]),
        _release("v0.1.39", ["JobManager-windows.zip"]),
        _release("v0.1.38", ["JobManager-macos.zip"]),
    ]
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json=payload if kwargs["params"]["page"] == 1 else [])

    monkeypatch.setattr(updater.sys, "platform", "win32")
    monkeypatch.setattr(updater.httpx, "get", get)
    releases, error = update_releases.list_available_releases()

    assert error == ""
    assert [release.version for release in releases] == ["0.1.40", "0.1.39"]
    assert all(release.asset_name == "JobManager-windows.zip" for release in releases)
    assert calls[0][1]["params"] == {"per_page": 100, "page": 1}


def test_release_selector_reports_api_error(monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "win32")
    monkeypatch.setattr(updater.httpx, "get", lambda *args, **kwargs: httpx.Response(403))

    releases, error = update_releases.list_available_releases()

    assert releases == []
    assert "HTTP 403" in error


def test_release_selector_reports_network_error(monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "win32")

    def fail(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(updater.httpx, "get", fail)
    releases, error = update_releases.list_available_releases()

    assert releases == []
    assert "ConnectError" in error
