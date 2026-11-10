from __future__ import annotations

import threading
import io
import urllib.error

import pytest

from app.services import ollama_runtime


def test_uses_bundled_ollama_runtime_in_place(tmp_path, monkeypatch):
    root = tmp_path / "bundle"
    executable = root / "ollama-runtime" / "ollama.exe"
    executable.parent.mkdir(parents=True)
    executable.write_text("runtime")
    monkeypatch.setattr(ollama_runtime.sys, "frozen", True, raising=False)
    monkeypatch.setattr(ollama_runtime.sys, "_MEIPASS", str(root), raising=False)
    monkeypatch.setattr(ollama_runtime.sys, "platform", "win32")

    assert ollama_runtime.ollama_executable() == str(executable)


def test_prepares_local_fallback_in_background(monkeypatch):
    ready = threading.Event()
    monkeypatch.setattr(ollama_runtime, "ensure_model", ready.set)

    ollama_runtime.prepare_local_fallback()

    assert ready.wait(2)


def test_owned_server_is_waited_for_after_termination(monkeypatch):
    seen = []

    class Process:
        def poll(self):
            return None

        def terminate(self):
            seen.append("terminate")

        def wait(self, timeout=None):
            seen.append(("wait", timeout))

    monkeypatch.setattr(ollama_runtime, "_PROCESS", Process())
    ollama_runtime.stop_owned_server()
    assert seen == ["terminate", ("wait", 10)]


def test_ollama_chat_sends_images_and_json_mode(monkeypatch):
    seen = {}
    monkeypatch.setattr(ollama_runtime, "ensure_model", lambda: None)

    def request(path, payload, timeout):
        seen.update(path=path, payload=payload, timeout=timeout)
        return {"message": {"content": '{"ok": true}'}}

    monkeypatch.setattr(ollama_runtime, "_request", request)
    assert ollama_runtime.chat("qwen3-vl:4b", "Review this drawing.", [b"image"]) == '{"ok": true}'
    message = seen["payload"]["messages"][0]
    assert seen["path"] == "/api/chat"
    assert message["images"] == ["aW1hZ2U="]
    assert seen["payload"]["format"] == "json" and seen["payload"]["stream"] is False
    assert seen["payload"]["options"]["num_ctx"] == 16384


def test_http_error_includes_ollama_detail_and_diagnostic_code(monkeypatch):
    def fail(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {},
                                     io.BytesIO(b'{"error":"model does not support images"}'))

    monkeypatch.setattr(ollama_runtime.urllib.request, "urlopen", fail)
    with pytest.raises(ollama_runtime.OllamaHTTPError, match="model does not support images") as error:
        ollama_runtime._request("/api/chat", {"model": "test"})
    assert error.value.status == 400
    assert error.value.path == "/api/chat"
    assert error.value.category == "image_or_vision"


def test_http_error_without_json_keeps_status(monkeypatch):
    def fail(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(b"not json"))

    monkeypatch.setattr(ollama_runtime.urllib.request, "urlopen", fail)
    with pytest.raises(ollama_runtime.OllamaHTTPError, match="HTTP 400"):
        ollama_runtime._request("/api/chat", {})


def test_server_check_requires_ollama_version(monkeypatch):
    monkeypatch.setattr(ollama_runtime, "_request", lambda *args, **kwargs: {})
    with pytest.raises(RuntimeError, match="did not return an Ollama version"):
        ollama_runtime._check_server()
    monkeypatch.setattr(ollama_runtime, "_request", lambda *args, **kwargs: {"version": "0.40.15"})
    ollama_runtime._check_server()


def test_server_starts_with_fixed_loopback_port(monkeypatch, tmp_path):
    seen = {}
    checks = iter([False, True])

    def check():
        if not next(checks):
            raise RuntimeError("offline")

    class Process:
        def poll(self):
            return None

    def start(args, **kwargs):
        seen.update(args=args, env=kwargs["env"])
        return Process()

    monkeypatch.setattr(ollama_runtime, "_check_server", check)
    monkeypatch.setattr(ollama_runtime, "ollama_executable", lambda: str(tmp_path / "ollama"))
    monkeypatch.setattr(ollama_runtime, "_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(ollama_runtime.subprocess, "Popen", start)
    monkeypatch.setattr(ollama_runtime, "_PROCESS", None)
    ollama_runtime.ensure_server()
    assert seen["args"] == [str(tmp_path / "ollama"), "serve"]
    assert seen["env"]["OLLAMA_HOST"] == "127.0.0.1:11434"
    assert seen["env"]["OLLAMA_MODELS"] == str(tmp_path / "data" / "models")


def test_model_preparation_checks_download_status(monkeypatch):
    calls = []
    monkeypatch.setattr(ollama_runtime, "ensure_server", lambda: None)

    def request(path, payload=None, timeout=10):
        calls.append((path, payload))
        return {"models": []} if path == "/api/tags" else {"status": "success"}

    monkeypatch.setattr(ollama_runtime, "_request", request)
    ollama_runtime.ensure_model()
    assert calls == [("/api/tags", None), ("/api/pull", {"name": ollama_runtime.OLLAMA_MODEL, "stream": False})]
    monkeypatch.setattr(ollama_runtime, "_request",
                        lambda path, payload=None, **kwargs:
                        {"models": []} if path == "/api/tags" else {"error": "failed"})
    with pytest.raises(RuntimeError, match="did not confirm"):
        ollama_runtime.ensure_model()


def test_chat_retries_without_json_mode_on_empty_content(monkeypatch):
    from app.services import ollama_runtime as rt

    calls = []

    def fake_request(path, payload=None, timeout=10):
        calls.append(payload)
        content = "" if "format" in payload else '{"ok": true}'
        return {"message": {"content": content}}

    monkeypatch.setattr(rt, "ensure_model", lambda: None)
    monkeypatch.setattr(rt, "_request", fake_request)
    assert rt.chat("m", "p", []) == '{"ok": true}'
    assert len(calls) == 2 and "format" not in calls[1]


def test_chat_reports_response_error_code(monkeypatch):
    import pytest
    from app.services import ollama_runtime as rt

    monkeypatch.setattr(rt, "ensure_model", lambda: None)
    monkeypatch.setattr(rt, "_request", lambda *a, **k: {"message": {"content": "", "thinking": "x"}})
    with pytest.raises(rt.OllamaResponseError) as info:
        rt.chat("m", "p", [])
    assert info.value.code == "thinking_only"
