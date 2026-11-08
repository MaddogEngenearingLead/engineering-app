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
_LOCK = threading.RLock()
_MODEL_LOCK = threading.Lock()
_PROCESS: subprocess.Popen | None = None
_PREPARING = False


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
    relative = ("ollama.exe" if sys.platform.startswith("win")
                else "Ollama.app/Contents/Resources/ollama")
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
    except (OSError, TimeoutError, urllib.error.URLError, ValueError) as exc:
        raise RuntimeError(f"Ollama request failed: {exc}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Ollama returned an invalid response.")
    return result


def chat(model: str, prompt: str, images: list[bytes]) -> str:
    ensure_model()
    reply = _request("/api/chat", {
        "model": model,
        "messages": [{"role": "user", "content": prompt,
                      "images": [base64.b64encode(image).decode("ascii") for image in images]}],
        "format": "json",
        "stream": False,
    }, timeout=900)
    message = reply.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content:
        raise RuntimeError("Ollama returned no text answer.")
    return content


def ensure_server(timeout: float = 60) -> None:
    global _PROCESS
    with _LOCK:
        try:
            _request("/api/version")
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
            if _PROCESS.poll() is not None:
                raise RuntimeError("The Ollama server stopped during startup.")
            try:
                _request("/api/version")
                return
            except RuntimeError:
                time.sleep(0.5)
        raise RuntimeError("Timed out waiting for the local Ollama server.")


def ensure_model() -> None:
    with _MODEL_LOCK:
        ensure_server()
        tags = _request("/api/tags", timeout=30).get("models", [])
        if any(model.get("name") == OLLAMA_MODEL or model.get("model") == OLLAMA_MODEL
               for model in tags if isinstance(model, dict)):
            return
        _request("/api/pull", {"name": OLLAMA_MODEL, "stream": False}, timeout=3600)


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


atexit.register(stop_owned_server)
