"""Create shareable scan failure reports without source documents or credentials."""
from __future__ import annotations

import json
import platform
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.services.ai_review import AIError
from app.services.ollama_runtime import OllamaHTTPError, OllamaResponseError, OLLAMA_MODEL
from app.version import __version__


def error_directory(jobs_directory: Path) -> Path:
    """Keep reports beside the jobs directory, including portable Jobs folders."""
    return jobs_directory.resolve().parent / "error"


def write_failure_report(directory: Path, job_number: str, stage: str, exc: Exception) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    failures = []
    frames = []
    seen = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, AIError):
            failures.extend(current.failures)
        if isinstance(current, OllamaHTTPError):
            failures.append({"provider": "ollama", "http_status": current.status,
                             "endpoint": current.path, "category": current.category,
                             "model": OLLAMA_MODEL})
        if isinstance(current, OllamaResponseError):
            failures.append({"provider": "ollama", "response_error": current.code,
                             "model": OLLAMA_MODEL})
        frames.append({
            "exception_type": type(current).__name__,
            "frames": [{"file": Path(frame.filename).name, "function": frame.name, "line": frame.lineno}
                       for frame in traceback.extract_tb(current.__traceback__)],
        })
        current = current.__cause__
    report = {
        "format_version": 1,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "app_version": __version__,
        "platform": platform.system(),
        "architecture": platform.machine(),
        "job_number": job_number,
        "stage": stage,
        "provider_failures": failures,
        "exception_chain": frames,
        "privacy_note": "No exception messages, document content, API keys, or file paths are included.",
    }
    path = directory / f"scan-failure-{uuid.uuid4().hex}.json"
    with path.open("x", encoding="utf-8") as file:
        json.dump(report, file, indent=2)
        file.write("\n")
    return path
