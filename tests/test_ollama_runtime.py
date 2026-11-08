from __future__ import annotations

import threading

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
