"""Start the bundled Ollama runtime and prepare the local vision fallback."""
from __future__ import annotations

import atexit
import base64
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

OLLAMA_MODEL = "qwen3-vl:4b"
OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_CONTEXT_LENGTH = 16384
_LOCK = threading.RLock()
_MODEL_LOCK = threading.Lock()
_PROCESS: subprocess.Popen | None = None
_PREPARING = False


class OllamaHTTPError(RuntimeError):
    def __init__(self, path: str, status: int, detail: str):
        self.path = path
        self.status = status
        self.category = _error_category(detail)
        super().__init__(f"Ollama {path} returned HTTP {status}" + (f": {detail}" if detail else "."))


class OllamaResponseError(RuntimeError):
    """Ollama answered but gave nothing usable; `code` is safe to include in reports."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _error_category(detail: str) -> str:
    text = detail.lower()
    if "memory" in text or "out of memory" in text:
        return "memory"
    if "context" in text:
        return "context"
    if "vision" in text or "image" in text:
        return "image_or_vision"
    if "model" in text:
        return "model"
    return "other"


def _data_dir() -> Path:
    if sys.platform.startswith("win"):
        root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        root = str(Path.home() / "Library" / "Application Support")
    else:
        root = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(root) / "EngineeringApp" / "ollama"


def _bundled_executable() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    relative = "ollama.exe" if sys.platform.startswith("win") else "ollama"
    path = Path(getattr(sys, "_MEIPASS", "")) / "ollama-runtime" / relative
    return path if path.is_file() and (sys.platform.startswith("win") or os.access(path, os.X_OK)) else None


def ollama_executable() -> str | None:
    bundled = _bundled_executable()
    if bundled:
        return str(bundled)
    system = shutil.which("ollama")
    return system


def _request(path: str, payload: dict | None = None, timeout: float = 10) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        OLLAMA_URL + path, data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read(8192))
            detail = body.get("error", "") if isinstance(body, dict) else ""
            if not isinstance(detail, str):
                detail = ""
        except (OSError, ValueError):
            detail = ""
        raise OllamaHTTPError(path, exc.code, " ".join(detail.split())[:500]) from exc
    except (OSError, TimeoutError, urllib.error.URLError, ValueError) as exc:
        raise RuntimeError(f"Ollama request failed: {exc}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Ollama returned an invalid response.")
    return result


def _chat_once(model: str, prompt: str, images: list[bytes], json_mode: bool) -> str:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt,
                      "images": [base64.b64encode(image).decode("ascii") for image in images]}],
        "stream": False,
        "think": False,
        "options": {"num_ctx": OLLAMA_CONTEXT_LENGTH},
    }
    if json_mode:
        payload["format"] = "json"
    reply = _request("/api/chat", payload, timeout=900)
    message = reply.get("message")
    if not isinstance(message, dict):
        raise OllamaResponseError("invalid_message", "Ollama returned no message.")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        code = "thinking_only" if message.get("thinking") else "empty_content"
        raise OllamaResponseError(code, "Ollama returned no text answer.")
    return content


def chat(model: str, prompt: str, images: list[bytes]) -> str:
    ensure_model()
    # JSON mode can yield empty output on some vision models; retry once without it.
    try:
        return _chat_once(model, prompt, images, json_mode=True)
    except OllamaResponseError:
        return _chat_once(model, prompt, images, json_mode=False)


def ensure_server(timeout: float = 60) -> None:
    global _PROCESS
    with _LOCK:
        try:
            _check_server()
            return
        except RuntimeError:
            pass
        executable = ollama_executable()
        if not executable:
            raise RuntimeError("The bundled Ollama runtime is unavailable.")
        env = os.environ.copy()
        env["OLLAMA_HOST"] = "127.0.0.1:11434"
        env["OLLAMA_MODELS"] = str(_data_dir() / "models")
        try:
            _PROCESS = subprocess.Popen(
                [executable, "serve"], cwd=str(Path(executable).parent), env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            raise RuntimeError(f"Could not start Ollama: {exc}") from exc
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                _check_server()
                return
            except RuntimeError:
                if _PROCESS.poll() is not None:
                    raise RuntimeError("The Ollama server stopped during startup; "
                                       "port 11434 may be occupied or unavailable.")
                time.sleep(0.5)
        if _PROCESS.poll() is None:
            _PROCESS.terminate()
        raise RuntimeError("Timed out waiting for the local Ollama server.")


def _check_server() -> None:
    response = _request("/api/version")
    if not isinstance(response.get("version"), str) or not response["version"].strip():
        raise RuntimeError("The service on port 11434 did not return an Ollama version.")


def ensure_model() -> None:
    with _MODEL_LOCK:
        ensure_server()
        tags = _request("/api/tags", timeout=30).get("models", [])
        if not isinstance(tags, list):
            raise RuntimeError("Ollama returned an invalid model list.")
        if any(model.get("name") == OLLAMA_MODEL or model.get("model") == OLLAMA_MODEL
               for model in tags if isinstance(model, dict)):
            return
        result = _request("/api/pull", {"name": OLLAMA_MODEL, "stream": False}, timeout=3600)
        if result.get("status") != "success":
            raise RuntimeError("Ollama did not confirm the vision model download succeeded.")


def prepare_local_fallback() -> None:
    """Run on application startup; keep model download and server startup off the UI thread."""
    global _PREPARING
    with _LOCK:
        if _PREPARING:
            return
        _PREPARING = True

    def prepare():
        try:
            ensure_model()
            logger.info("Local Ollama fallback is ready (%s).", OLLAMA_MODEL)
        except Exception:
            logger.exception("Could not prepare the local Ollama fallback.")
        finally:
            global _PREPARING
            with _LOCK:
                _PREPARING = False

    threading.Thread(target=prepare, name="ollama-startup", daemon=True).start()


def stop_owned_server() -> None:
    if _PROCESS is not None and _PROCESS.poll() is None:
        _PROCESS.terminate()
        try:
            _PROCESS.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _PROCESS.kill()
            _PROCESS.wait()


atexit.register(stop_owned_server)
